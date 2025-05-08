import dataclasses
from collections.abc import Generator
from typing import cast
from unittest.mock import ANY, MagicMock, patch

import bluesky.plan_stubs as bps
import pytest
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from bluesky.utils import Msg
from dodal.devices.aperturescatterguard import ApertureValue
from dodal.devices.backlight import BacklightPosition
from dodal.devices.mx_phase1.beamstop import BeamstopPositions
from dodal.devices.oav.oav_parameters import OAVParameters
from dodal.devices.oav.pin_image_recognition import PinTipDetection
from ophyd_async.testing import get_mock_put

from mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan import (
    BeamlineSpecificFGSFeatures,
    _fire_xray_centre_result_event,
)
from mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan import (
    ConstructBeamlineSpecificFeatures,
    detect_grid_and_do_gridscan,
    grid_detect_then_xray_centre,
)
from mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback import (
    ispyb_activation_wrapper,
)
from mx_bluesky.common.parameters.constants import PlanNameConstants
from mx_bluesky.hyperion.experiment_plans.hyperion_grid_detect_then_xray_centre_plan import (
    hyperion_grid_detect_then_xray_centre,
)
from mx_bluesky.hyperion.parameters.constants import CONST
from mx_bluesky.hyperion.parameters.device_composites import (
    GridDetectThenXRayCentreComposite,
    HyperionGridDetectThenXRayCentreComposite,
)
from mx_bluesky.hyperion.parameters.gridscan import (
    GridScanWithEdgeDetect,
    HyperionSpecifiedThreeDGridScan,
)

from ....conftest import (
    TEST_RESULT_LARGE,
    OavGridSnapshotTestEvents,
    simulate_xrc_result,
)
from .conftest import FLYSCAN_RESULT_LOW, FLYSCAN_RESULT_MED, sim_fire_event_on_open_run


def _fake_flyscan(*args):
    yield from _fire_xray_centre_result_event([FLYSCAN_RESULT_MED, FLYSCAN_RESULT_LOW])


def test_full_grid_scan(
    hyperion_fgs_params: HyperionSpecifiedThreeDGridScan,
    test_config_files: dict[str, str],
):
    devices = MagicMock()
    plan = hyperion_grid_detect_then_xray_centre(
        devices,
        cast(GridScanWithEdgeDetect, hyperion_fgs_params),
        test_config_files["oav_config_json"],
    )
    assert isinstance(plan, Generator)


@pytest.fixture()
def construct_beamline_specific(
    beamline_specific: BeamlineSpecificFGSFeatures,
) -> ConstructBeamlineSpecificFeatures:
    return lambda xrc_composite, xrc_parameters: beamline_specific


@pytest.mark.timeout(2)
@patch(
    "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.common_flyscan_xray_centre",
    autospec=True,
)
async def test_detect_grid_and_do_gridscan_in_real_RE(
    mock_flyscan: MagicMock,
    pin_tip_detection_with_found_pin: PinTipDetection,
    grid_detect_devices_with_oav_config_params: GridDetectThenXRayCentreComposite,
    RE: RunEngine,
    test_full_grid_scan_params: GridScanWithEdgeDetect,
    test_config_files: dict,
    construct_beamline_specific: ConstructBeamlineSpecificFeatures,
):
    composite = grid_detect_devices_with_oav_config_params
    RE(
        ispyb_activation_wrapper(
            _do_detect_grid_and_gridscan_then_wait_for_backlight(
                composite,
                test_config_files,
                test_full_grid_scan_params,
                construct_beamline_specific,
            ),
            test_full_grid_scan_params,
        )
    )

    # Check backlight was moved OUT
    get_mock_put(composite.backlight.position).assert_called_once_with(
        BacklightPosition.OUT, wait=ANY
    )

    # Check aperture was changed to SMALL
    assert (
        await composite.aperture_scatterguard.selected_aperture.get_value()
        == ApertureValue.SMALL
    )

    # Check we called out to underlying fast grid scan plan
    mock_flyscan.assert_called_once_with(ANY, ANY, ANY)


def _do_detect_grid_and_gridscan_then_wait_for_backlight(
    composite,
    test_config_files,
    test_full_grid_scan_params,
    construct_beamline_specific_xrc_features,
):
    yield from detect_grid_and_do_gridscan(
        composite,
        parameters=test_full_grid_scan_params,
        oav_params=OAVParameters("xrayCentring", test_config_files["oav_config_json"]),
        xrc_params_type=HyperionSpecifiedThreeDGridScan,
        construct_beamline_specific=construct_beamline_specific_xrc_features,
    )
    yield from bps.wait(CONST.WAIT.GRID_READY_FOR_DC)


@pytest.mark.timeout(2)
@patch(
    "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.common_flyscan_xray_centre",
    autospec=True,
)
def test_when_full_grid_scan_run_then_parameters_sent_to_fgs_as_expected(
    mock_flyscan: MagicMock,
    grid_detect_devices_with_oav_config_params: GridDetectThenXRayCentreComposite,
    RE: RunEngine,
    test_full_grid_scan_params: GridScanWithEdgeDetect,
    test_config_files: dict,
    pin_tip_detection_with_found_pin: PinTipDetection,
    construct_beamline_specific: ConstructBeamlineSpecificFeatures,
):
    oav_params = OAVParameters("xrayCentring", test_config_files["oav_config_json"])

    RE(
        ispyb_activation_wrapper(
            detect_grid_and_do_gridscan(
                grid_detect_devices_with_oav_config_params,
                parameters=test_full_grid_scan_params,
                oav_params=oav_params,
                xrc_params_type=HyperionSpecifiedThreeDGridScan,
                construct_beamline_specific=construct_beamline_specific,
            ),
            test_full_grid_scan_params,
        )
    )

    params: HyperionSpecifiedThreeDGridScan = mock_flyscan.call_args[0][1]

    assert params.detector_params.num_triggers == 180
    assert params.FGS_params.x_axis.full_steps == 15
    assert params.FGS_params.y_axis.end == pytest.approx(-0.0649, 0.001)

    # Parameters can be serialized
    params.model_dump_json()


@patch(
    "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.grid_detection_plan",
    autospec=True,
)
@patch(
    "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.common_flyscan_xray_centre",
    autospec=True,
)
def test_detect_grid_and_do_gridscan_does_not_activate_ispyb_callback(
    mock_flyscan,
    mock_grid_detection_plan,
    grid_detect_devices_with_oav_config_params: GridDetectThenXRayCentreComposite,
    sim_run_engine: RunEngineSimulator,
    test_full_grid_scan_params: GridScanWithEdgeDetect,
    test_config_files: dict[str, str],
    construct_beamline_specific: ConstructBeamlineSpecificFeatures,
):
    mock_grid_detection_plan.return_value = iter([Msg("save_oav_grids")])
    sim_run_engine.add_handler_for_callback_subscribes()
    sim_run_engine.add_callback_handler_for_multiple(
        "save_oav_grids",
        [
            [
                (
                    "descriptor",
                    OavGridSnapshotTestEvents.test_descriptor_document_oav_snapshot,  # type: ignore
                ),
                (
                    "event",
                    OavGridSnapshotTestEvents.test_event_document_oav_snapshot_xy,  # type: ignore
                ),
                (
                    "event",
                    OavGridSnapshotTestEvents.test_event_document_oav_snapshot_xz,  # type: ignore
                ),
            ]
        ],
    )

    msgs = sim_run_engine.simulate_plan(
        detect_grid_and_do_gridscan(
            grid_detect_devices_with_oav_config_params,
            test_full_grid_scan_params,
            OAVParameters("xrayCentring", test_config_files["oav_config_json"]),
            xrc_params_type=HyperionSpecifiedThreeDGridScan,
            construct_beamline_specific=construct_beamline_specific,
        )
    )

    activations = [
        msg
        for msg in msgs
        if msg.command == "open_run"
        and "GridscanISPyBCallback" in msg.kwargs["activate_callbacks"]
    ]
    assert not activations


@pytest.fixture()
@patch(
    "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.grid_detection_plan",
    autospec=True,
)
@patch(
    "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.common_flyscan_xray_centre",
    autospec=True,
    side_effect=_fake_flyscan,
)
def msgs_from_simulated_grid_detect_then_xray_centre(
    mock_flyscan,
    mock_grid_detection_plan,
    sim_run_engine: RunEngineSimulator,
    grid_detect_devices_with_oav_config_params: GridDetectThenXRayCentreComposite,
    test_full_grid_scan_params: GridScanWithEdgeDetect,
    test_config_files: dict[str, str],
    construct_beamline_specific: ConstructBeamlineSpecificFeatures,
):
    mock_grid_detection_plan.return_value = iter(
        [
            Msg("save_oav_grids"),
            Msg(
                "open_run",
                run=CONST.PLAN.FLYSCAN_RESULTS,
                xray_centre_results=[dataclasses.asdict(FLYSCAN_RESULT_MED)],
            ),
        ]
    )

    sim_run_engine.add_handler_for_callback_subscribes()
    sim_fire_event_on_open_run(sim_run_engine, CONST.PLAN.FLYSCAN_RESULTS)
    sim_run_engine.add_callback_handler_for_multiple(
        "save_oav_grids",
        [
            [
                (
                    "descriptor",
                    OavGridSnapshotTestEvents.test_descriptor_document_oav_snapshot,  # type: ignore
                ),
                (
                    "event",
                    OavGridSnapshotTestEvents.test_event_document_oav_snapshot_xy,  # type: ignore
                ),
                (
                    "event",
                    OavGridSnapshotTestEvents.test_event_document_oav_snapshot_xz,  # type: ignore
                ),
            ]
        ],
    )
    return sim_run_engine.simulate_plan(
        grid_detect_then_xray_centre(
            grid_detect_devices_with_oav_config_params,
            test_full_grid_scan_params,
            xrc_params_type=HyperionSpecifiedThreeDGridScan,
            construct_beamline_specific=construct_beamline_specific,
            oav_config=test_config_files["oav_config_json"],
        )
    )


def test_grid_detect_then_xray_centre_centres_on_the_first_flyscan_result(
    msgs_from_simulated_grid_detect_then_xray_centre: list[Msg],
):
    msgs = assert_message_and_return_remaining(
        msgs_from_simulated_grid_detect_then_xray_centre,
        lambda msg: msg.command == "set"
        and msg.obj.name == "smargon-x"
        and msg.args[0] == FLYSCAN_RESULT_MED.centre_of_mass_mm[0],
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "smargon-y"
        and msg.args[0] == FLYSCAN_RESULT_MED.centre_of_mass_mm[1],
    )
    assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "smargon-z"
        and msg.args[0] == FLYSCAN_RESULT_MED.centre_of_mass_mm[2],
    )


def test_grid_detect_then_xray_centre_activates_ispyb_callback(
    msgs_from_simulated_grid_detect_then_xray_centre: list[Msg],
):
    assert_message_and_return_remaining(
        msgs_from_simulated_grid_detect_then_xray_centre,
        lambda msg: msg.command == "open_run"
        and "GridscanISPyBCallback" in msg.kwargs["activate_callbacks"],
    )


def test_detect_grid_and_do_gridscan_waits_for_aperture_to_be_prepared_before_moving_in(
    msgs_from_simulated_grid_detect_then_xray_centre: list[Msg],
):
    msgs = assert_message_and_return_remaining(
        msgs_from_simulated_grid_detect_then_xray_centre,
        lambda msg: msg.command == "prepare"
        and msg.obj.name == "aperture_scatterguard"
        and msg.args[0] == ApertureValue.SMALL,
    )

    aperture_prepare_group = msgs[0].kwargs.get("group")

    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "wait"
        and msg.kwargs["group"] == aperture_prepare_group,
    )

    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "aperture_scatterguard-selected_aperture"
        and msg.args[0] == ApertureValue.SMALL,
    )


@patch(
    "mx_bluesky.hyperion.experiment_plans.grid_detect_then_xray_centre_plan.detect_grid_and_do_gridscan"
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.grid_detect_then_xray_centre_plan.XRayCentreEventHandler"
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.grid_detect_then_xray_centre_plan.change_aperture_then_move_to_xtal"
)
def test_grid_detect_then_xray_centre_plan_moves_beamstop_into_place(
    mock_change_aperture_then_move_to_xtal: MagicMock,
    mock_events_handler: MagicMock,
    mock_grid_detect_then_xray_centre: MagicMock,
    sim_run_engine: RunEngineSimulator,
    grid_detect_devices_with_oav_config_params: GridDetectThenXRayCentreComposite,
    test_full_grid_scan_params: GridScanWithEdgeDetect,
):
    flyscan_event_handler = MagicMock()
    flyscan_event_handler.xray_centre_results = "dummy"
    mock_events_handler.return_value = flyscan_event_handler

    mock_grid_detect_then_xray_centre.return_value = iter(
        [Msg("grid_detect_then_xray_centre")]
    )
    msgs = sim_run_engine.simulate_plan(
        grid_detect_then_xray_centre(
            grid_detect_devices_with_oav_config_params, test_full_grid_scan_params
        )
    )

    msgs = assert_message_and_return_remaining(
        msgs,
        predicate=lambda msg: msg.command == "set"
        and msg.obj.name == "beamstop-selected_pos"
        and msg.args[0] == BeamstopPositions.DATA_COLLECTION,
    )

    msgs = assert_message_and_return_remaining(
        msgs, predicate=lambda msg: msg.command == "grid_detect_then_xray_centre"
    )


@patch("bluesky.plan_stubs.sleep", autospec=True)
@patch(
    "mx_bluesky.common.experiment_plans.inner_plans.do_fgs.check_topup_and_wait_if_necessary",
)
@patch(
    "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.grid_detection_plan",
)
@patch(
    "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.GridDetectionCallback",
)
@patch(
    "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.create_parameters_for_flyscan_xray_centre",
)
def test_flyscan_xray_centre_pauses_and_unpauses_xbpm_feedback_in_correct_order(
    mock_create_parameters: MagicMock,
    mock_grid_detection_callback: MagicMock,
    mock_grid_detection_plan: MagicMock,
    mock_check_topup: MagicMock,
    mock_wait: MagicMock,
    sim_run_engine: RunEngineSimulator,
    test_full_grid_scan_params: GridScanWithEdgeDetect,
    grid_detect_devices_with_oav_config_params: HyperionGridDetectThenXRayCentreComposite,
    test_config_files,
    construct_beamline_specific,
    hyperion_fgs_params,
):
    mock_create_parameters.return_value = hyperion_fgs_params
    simulate_xrc_result(
        sim_run_engine,
        grid_detect_devices_with_oav_config_params.zocalo,
        TEST_RESULT_LARGE,
    )

    msgs = sim_run_engine.simulate_plan(
        detect_grid_and_do_gridscan(
            grid_detect_devices_with_oav_config_params,
            test_full_grid_scan_params,
            OAVParameters("xrayCentring", test_config_files["oav_config_json"]),
            xrc_params_type=HyperionSpecifiedThreeDGridScan,
            construct_beamline_specific=construct_beamline_specific,
        )
    )

    # Assert order: pause -> open run -> close run -> unpause (set attenuator)
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "trigger" and msg.obj.name == "xbpm_feedback",
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "open_run"
        and msg.run == PlanNameConstants.GRIDSCAN_OUTER,
    )

    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "close_run"
        and msg.run == PlanNameConstants.GRIDSCAN_OUTER,
    )

    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "attenuator"
        and msg.args == (1.0,),
    )
