import dataclasses
from unittest.mock import AsyncMock, MagicMock, patch

import numpy
import pytest
from bluesky.protocols import Location
from dodal.devices.oav.oav_parameters import OAVParameters
from dodal.devices.oav.pin_image_recognition import PinTipDetection
from dodal.devices.synchrotron import SynchrotronMode
from ophyd.sim import NullStatus
from ophyd_async.core import set_mock_value

from mx_bluesky.common.parameters.robot_load import RobotLoadAndEnergyChange
from mx_bluesky.common.utils.exceptions import WarningException
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
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect
from mx_bluesky.hyperion.parameters.rotation import MultiRotationScan

from ....conftest import pin_tip_edge_data, raw_params_from_file


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
    "mx_bluesky.hyperion.experiment_plans.robot_load_then_centre_plan.pin_centre_then_xray_centre_plan",
    return_value=iter([]),
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.robot_load_then_centre_plan.robot_load_and_change_energy_plan",
    return_value=iter([]),
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.load_centre_collect_full_plan.multi_rotation_scan",
    return_value=iter([]),
)
def test_load_centre_collect_full_plan_happy_path_invokes_all_steps(
    mock_rotation_scan: MagicMock,
    mock_full_robot_load_plan: MagicMock,
    mock_pin_centre_then_xray_centre_plan: MagicMock,
    composite: LoadCentreCollectComposite,
    load_centre_collect_params: LoadCentreCollect,
    oav_parameters_for_rotation: OAVParameters,
    sim_run_engine,
):
    sim_run_engine.simulate_plan(
        load_centre_collect_full_plan(
            composite, load_centre_collect_params, oav_parameters_for_rotation
        )
    )

    mock_full_robot_load_plan.assert_called_once()
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
