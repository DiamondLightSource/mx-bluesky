import dataclasses
from unittest.mock import AsyncMock, MagicMock, patch

import numpy
import pytest
from bluesky.protocols import Location
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from bluesky.utils import Msg
from dodal.devices.oav.oav_parameters import OAVParameters
from dodal.devices.oav.pin_image_recognition import PinTipDetection
from dodal.devices.synchrotron import SynchrotronMode
from ophyd.sim import NullStatus
from ophyd_async.core import set_mock_value
from pydantic import ValidationError

from mx_bluesky.hyperion.exceptions import WarningException
from mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan import (
    CrystalNotFoundException,
)
from mx_bluesky.hyperion.experiment_plans.load_centre_collect_full_plan import (
    LoadCentreCollectComposite,
    load_centre_collect_full_plan,
)
from mx_bluesky.hyperion.experiment_plans.robot_load_then_centre_plan import (
    RobotLoadThenCentreComposite,
)
from mx_bluesky.hyperion.experiment_plans.rotation_scan_plan import (
    RotationScanComposite,
)
from mx_bluesky.hyperion.parameters.constants import CONST
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect
from mx_bluesky.hyperion.parameters.robot_load import RobotLoadAndEnergyChange
from mx_bluesky.hyperion.parameters.rotation import MultiRotationScan

from ....conftest import pin_tip_edge_data, raw_params_from_file
from .conftest import (
    FLYSCAN_RESULT_HIGH,
    FLYSCAN_RESULT_LOW,
    FLYSCAN_RESULT_MED,
    sim_fire_event_on_open_run,
)


def find_a_pin(pin_tip_detection):
    def set_good_position():
        set_mock_value(pin_tip_detection.triggered_tip, numpy.array([100, 110]))
        return NullStatus()

    return set_good_position


@pytest.fixture
def composite(
    robot_load_composite, fake_create_rotation_devices, sim_run_engine
) -> LoadCentreCollectComposite:
    rlaec_args = {
        field.name: getattr(robot_load_composite, field.name)
        for field in dataclasses.fields(robot_load_composite)
    }
    rotation_args = {
        field.name: getattr(fake_create_rotation_devices, field.name)
        for field in dataclasses.fields(fake_create_rotation_devices)
    }

    composite = LoadCentreCollectComposite(**(rlaec_args | rotation_args))
    minaxis = Location(setpoint=-2, readback=-2)
    maxaxis = Location(setpoint=2, readback=2)
    tip_x_px, tip_y_px, top_edge_array, bottom_edge_array = pin_tip_edge_data()
    sim_run_engine.add_handler(
        "locate", lambda _: minaxis, "smargon-x-low_limit_travel"
    )
    sim_run_engine.add_handler(
        "locate", lambda _: minaxis, "smargon-y-low_limit_travel"
    )
    sim_run_engine.add_handler(
        "locate", lambda _: minaxis, "smargon-z-low_limit_travel"
    )
    sim_run_engine.add_handler(
        "locate", lambda _: maxaxis, "smargon-x-high_limit_travel"
    )
    sim_run_engine.add_handler(
        "locate", lambda _: maxaxis, "smargon-y-high_limit_travel"
    )
    sim_run_engine.add_handler(
        "locate", lambda _: maxaxis, "smargon-z-high_limit_travel"
    )
    sim_run_engine.add_read_handler_for(
        composite.synchrotron.synchrotron_mode, SynchrotronMode.USER
    )
    sim_run_engine.add_read_handler_for(
        composite.synchrotron.top_up_start_countdown, -1
    )
    sim_run_engine.add_read_handler_for(
        composite.pin_tip_detection.triggered_top_edge, top_edge_array
    )
    sim_run_engine.add_read_handler_for(
        composite.pin_tip_detection.triggered_bottom_edge, bottom_edge_array
    )
    zoom_levels_list = ["1.0x", "3.0x", "5.0x", "7.5x", "10.0x"]
    composite.oav.zoom_controller.level.describe = AsyncMock(
        return_value={"level": {"choices": zoom_levels_list}}
    )
    set_mock_value(composite.oav.zoom_controller.level, "7.5x")

    sim_run_engine.add_read_handler_for(
        composite.pin_tip_detection.triggered_tip, (tip_x_px, tip_y_px)
    )
    composite.pin_tip_detection.trigger = MagicMock(
        side_effect=find_a_pin(composite.pin_tip_detection)
    )
    return composite


@pytest.fixture
def load_centre_collect_params():
    params = raw_params_from_file(
        "tests/test_data/parameter_json_files/good_test_load_centre_collect_params.json"
    )
    return LoadCentreCollect(**params)


@pytest.fixture
def load_centre_collect_with_top_n_params():
    params = raw_params_from_file(
        "tests/test_data/parameter_json_files/load_centre_collect_params_top_n_by_max_count.json"
    )
    return LoadCentreCollect(**params)


@pytest.fixture
def grid_detection_callback_with_detected_grid():
    with patch(
        "mx_bluesky.hyperion.experiment_plans.grid_detect_then_xray_centre_plan.GridDetectionCallback",
        autospec=True,
    ) as callback:
        callback.return_value.get_grid_parameters.return_value = {
            "transmission_frac": 1.0,
            "exposure_time_s": 0,
            "x_start_um": 0,
            "y_start_um": 0,
            "y2_start_um": 0,
            "z_start_um": 0,
            "z2_start_um": 0,
            "x_steps": 10,
            "y_steps": 10,
            "z_steps": 10,
            "x_step_size_um": 0.1,
            "y_step_size_um": 0.1,
            "z_step_size_um": 0.1,
        }
        yield callback


def test_can_serialize_load_centre_collect_params(load_centre_collect_params):
    load_centre_collect_params.model_dump_json()


def test_can_serialize_load_centre_collect_robot_load_params(
    load_centre_collect_params,
):
    load_centre_collect_params.robot_load_then_centre.model_dump_json()


def test_can_serialize_load_centre_collect_multi_rotation_scan(
    load_centre_collect_params,
):
    load_centre_collect_params.multi_rotation_scan.model_dump_json()


def test_can_serialize_load_centre_collect_single_rotation_scans(
    load_centre_collect_params,
):
    list(load_centre_collect_params.multi_rotation_scan.single_rotation_scans)[
        0
    ].model_dump_json()


@patch(
    "mx_bluesky.hyperion.experiment_plans.robot_load_then_centre_plan.pin_centre_then_flyscan_plan",
    return_value=iter(
        [
            Msg(
                "open_run",
                flyscan_results=[dataclasses.asdict(FLYSCAN_RESULT_MED)],
                run=CONST.PLAN.FLYSCAN_RESULTS,
            ),
            Msg("close_run"),
        ]
    ),
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.robot_load_then_centre_plan.robot_load_and_change_energy_plan",
    return_value=iter([Msg(command="robot_load_and_change_energy")]),
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.load_centre_collect_full_plan.multi_rotation_scan",
    return_value=iter([Msg(command="multi_rotation_scan")]),
)
def test_collect_full_plan_happy_path_invokes_all_steps_and_centres_on_best_flyscan_result(
    mock_rotation_scan: MagicMock,
    mock_full_robot_load_plan: MagicMock,
    mock_pin_centre_then_xray_centre_plan: MagicMock,
    composite: LoadCentreCollectComposite,
    load_centre_collect_params: LoadCentreCollect,
    oav_parameters_for_rotation: OAVParameters,
    sim_run_engine,
):
    sim_run_engine.add_handler_for_callback_subscribes()
    sim_fire_event_on_open_run(sim_run_engine, CONST.PLAN.FLYSCAN_RESULTS)
    msgs = sim_run_engine.simulate_plan(
        load_centre_collect_full_plan(
            composite, load_centre_collect_params, oav_parameters_for_rotation
        )
    )

    msgs = assert_message_and_return_remaining(
        msgs, lambda msg: msg.command == "open_run" and "flyscan_results" in msg.kwargs
    )
    # msgs = assert_message_and_return_remaining(
    #     msgs, lambda msg: msg.command == "set" and msg.args[0] == ApertureValue.MEDIUM
    # )
    # msgs = assert_message_and_return_remaining(
    #     msgs,
    #     lambda msg: msg.command == "set"
    #     and msg.obj.name == "smargon-x"
    #     and msg.args[0] == 0.1,
    # )
    # msgs = assert_message_and_return_remaining(
    #     msgs,
    #     lambda msg: msg.command == "set"
    #     and msg.obj.name == "smargon-y"
    #     and msg.args[0] == 0.2,
    # )
    # msgs = assert_message_and_return_remaining(
    #     msgs,
    #     lambda msg: msg.command == "set"
    #     and msg.obj.name == "smargon-z"
    #     and msg.args[0] == 0.3,
    # )
    msgs = assert_message_and_return_remaining(
        msgs, lambda msg: msg.command == "multi_rotation_scan"
    )

    robot_load_energy_change_composite = mock_full_robot_load_plan.mock_calls[0].args[0]
    robot_load_energy_change_params = mock_full_robot_load_plan.mock_calls[0].args[1]
    assert isinstance(robot_load_energy_change_composite, RobotLoadThenCentreComposite)
    assert isinstance(robot_load_energy_change_params, RobotLoadAndEnergyChange)
    mock_pin_centre_then_xray_centre_plan.assert_called_once()
    mock_rotation_scan.assert_called_once()
    rotation_scan_composite = mock_rotation_scan.mock_calls[0].args[0]
    rotation_scan_params = mock_rotation_scan.mock_calls[0].args[1]
    assert isinstance(rotation_scan_composite, RotationScanComposite)
    assert isinstance(rotation_scan_params, MultiRotationScan)


@patch(
    "mx_bluesky.hyperion.experiment_plans.load_centre_collect_full_plan.multi_rotation_scan",
    return_value=iter([]),
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.robot_load_and_change_energy.set_energy_plan",
    new=MagicMock(),
)
def test_load_centre_collect_full_plan_skips_collect_if_pin_tip_not_found(
    mock_rotation_scan: MagicMock,
    composite: LoadCentreCollectComposite,
    load_centre_collect_params: LoadCentreCollect,
    oav_parameters_for_rotation: OAVParameters,
    sim_run_engine,
):
    sim_run_engine.add_read_handler_for(
        composite.pin_tip_detection.triggered_tip, PinTipDetection.INVALID_POSITION
    )
    sim_run_engine.add_read_handler_for(composite.oav.microns_per_pixel_x, 1.58)
    sim_run_engine.add_read_handler_for(composite.oav.microns_per_pixel_y, 1.58)

    with pytest.raises(WarningException, match="Pin tip centring failed"):
        sim_run_engine.simulate_plan(
            load_centre_collect_full_plan(
                composite, load_centre_collect_params, oav_parameters_for_rotation
            )
        )

    mock_rotation_scan.assert_not_called()


@patch(
    "mx_bluesky.hyperion.experiment_plans.load_centre_collect_full_plan.multi_rotation_scan",
    return_value=iter([]),
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.robot_load_and_change_energy.set_energy_plan",
    new=MagicMock(),
)
def test_load_centre_collect_full_plan_skips_collect_if_no_diffraction(
    mock_rotation_scan: MagicMock,
    composite: LoadCentreCollectComposite,
    load_centre_collect_params: LoadCentreCollect,
    oav_parameters_for_rotation: OAVParameters,
    sim_run_engine,
    grid_detection_callback_with_detected_grid,
):
    sim_run_engine.add_read_handler_for(composite.oav.microns_per_pixel_x, 1.58)
    sim_run_engine.add_read_handler_for(composite.oav.microns_per_pixel_y, 1.58)

    with pytest.raises(CrystalNotFoundException):
        sim_run_engine.simulate_plan(
            load_centre_collect_full_plan(
                composite, load_centre_collect_params, oav_parameters_for_rotation
            )
        )

    mock_rotation_scan.assert_not_called()


def test_can_deserialize_top_n_by_max_count_params(
    load_centre_collect_with_top_n_params,
):
    assert (
        load_centre_collect_with_top_n_params.select_centres.name
        == "top_n_by_max_count"
    )
    assert load_centre_collect_with_top_n_params.select_centres.n == 5


def test_bad_selection_method_is_rejected():
    params = raw_params_from_file(
        "tests/test_data/parameter_json_files/load_centre_collect_params_top_n_by_max_count.json"
    )
    params["select_centres"]["name"] = "inject_bad_code_here"
    with pytest.raises(
        ValidationError,
        match=(
            "Input tag 'inject_bad_code_here' found using 'name' does not match any "
            "of the expected tags"
        ),
    ):
        LoadCentreCollect(**params)


def test_default_select_centres_is_top_n_by_max_count_n_is_1(
    load_centre_collect_params,
):
    assert load_centre_collect_params.select_centres.name == "top_n_by_max_count"
    assert load_centre_collect_params.select_centres.n == 1


@patch(
    "mx_bluesky.hyperion.experiment_plans.robot_load_then_centre_plan.pin_centre_then_flyscan_plan",
    new=MagicMock(
        return_value=iter(
            [
                Msg(
                    "open_run",
                    flyscan_results=[
                        dataclasses.asdict(r)
                        for r in [
                            FLYSCAN_RESULT_MED,
                            FLYSCAN_RESULT_HIGH,
                            FLYSCAN_RESULT_MED,
                            FLYSCAN_RESULT_LOW,
                            FLYSCAN_RESULT_MED,
                            FLYSCAN_RESULT_HIGH,
                        ]
                    ],
                    run=CONST.PLAN.FLYSCAN_RESULTS,
                ),
                Msg("close_run"),
            ]
        )
    ),
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.robot_load_then_centre_plan.robot_load_and_change_energy_plan",
    new=MagicMock(return_value=iter([Msg(command="robot_load_and_change_energy")])),
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.load_centre_collect_full_plan.multi_rotation_scan",
    new=MagicMock(
        side_effect=lambda _, __, ___: iter([Msg(command="multi_rotation_scan")])
    ),
)
def test_load_centre_collect_full_plan_multiple_centres(
    sim_run_engine: RunEngineSimulator,
    load_centre_collect_with_top_n_params: LoadCentreCollect,
    oav_parameters_for_rotation: OAVParameters,
    composite: LoadCentreCollectComposite,
):
    sim_run_engine.add_handler_for_callback_subscribes()
    sim_fire_event_on_open_run(sim_run_engine, CONST.PLAN.FLYSCAN_RESULTS)
    msgs = sim_run_engine.simulate_plan(
        load_centre_collect_full_plan(
            composite,
            load_centre_collect_with_top_n_params,
            oav_parameters_for_rotation,
        )
    )

    msgs = assert_message_and_return_remaining(
        msgs, lambda msg: msg.command == "robot_load_and_change_energy"
    )
    assert sum(1 for msg in msgs if msg.command == "robot_load_and_change_energy") == 1
    msgs = assert_message_and_return_remaining(
        msgs, lambda msg: msg.command == "open_run" and "flyscan_results" in msg.kwargs
    )
    # for expected_hit in [
    #     FLYSCAN_RESULT_HIGH,
    #     FLYSCAN_RESULT_HIGH,
    #     FLYSCAN_RESULT_MED,
    #     FLYSCAN_RESULT_MED,
    #     FLYSCAN_RESULT_MED,
    # ]:
    # msgs = assert_message_and_return_remaining(
    #     msgs,
    #     lambda msg: msg.command == "set" and msg.args[0] == ApertureValue.MEDIUM,
    # )
    # msgs = assert_message_and_return_remaining(
    #     msgs,
    #     lambda msg: msg.command == "set"
    #     and msg.obj.name == "smargon-x"
    #     and msg.args[0] == expected_hit.centre_of_mass_mm[0],
    # )
    # msgs = assert_message_and_return_remaining(
    #     msgs,
    #     lambda msg: msg.command == "set"
    #     and msg.obj.name == "smargon-y"
    #     and msg.args[0] == expected_hit.centre_of_mass_mm[1],
    # )
    # msgs = assert_message_and_return_remaining(
    #     msgs,
    #     lambda msg: msg.command == "set"
    #     and msg.obj.name == "smargon-z"
    #     and msg.args[0] == expected_hit.centre_of_mass_mm[2],
    # )
    msgs = assert_message_and_return_remaining(
        msgs, lambda msg: msg.command == "multi_rotation_scan"
    )
