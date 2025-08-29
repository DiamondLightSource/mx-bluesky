import dataclasses
from unittest.mock import ANY, MagicMock, call, patch

import bluesky.plan_stubs as bps
import pytest
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from bluesky.utils import Msg
from dodal.devices.aperturescatterguard import ApertureValue
from dodal.devices.backlight import InOut
from dodal.devices.mx_phase1.beamstop import BeamstopPositions
from dodal.devices.oav.oav_parameters import OAVParameters
from dodal.devices.oav.pin_image_recognition import PinTipDetection
from dodal.devices.smargon import CombinedMove
from ophyd_async.testing import get_mock_put

from mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan import (
    BeamlineSpecificFGSFeatures,
)
from mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan import (
    ConstructBeamlineSpecificFeatures,
    detect_grid_and_do_gridscan,
    grid_detect_then_xray_centre,
)
from mx_bluesky.common.experiment_plans.inner_plans.xrc_results_utils import (
    _fire_xray_centre_result_event,
)
from mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback import (
    ispyb_activation_wrapper,
)
from mx_bluesky.common.parameters.constants import (
    DocDescriptorNames,
    PlanGroupCheckpointConstants,
)
from mx_bluesky.common.parameters.gridscan import SpecifiedThreeDGridScan
from mx_bluesky.hyperion.parameters.device_composites import (
    GridDetectThenXRayCentreComposite,
)
from mx_bluesky.hyperion.parameters.gridscan import (
    GridScanWithEdgeDetect,
    HyperionSpecifiedThreeDGridScan,
)

from ....conftest import (
    OavGridSnapshotTestEvents,
)
from ...hyperion.experiment_plans.conftest import (
    FLYSCAN_RESULT_LOW,
    FLYSCAN_RESULT_MED,
    sim_fire_event_on_open_run,
)


def _fake_flyscan(*args):
    yield from _fire_xray_centre_result_event([FLYSCAN_RESULT_MED, FLYSCAN_RESULT_LOW])


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
    grid_detect_xrc_devices: GridDetectThenXRayCentreComposite,
    RE: RunEngine,
    test_full_grid_scan_params: GridScanWithEdgeDetect,
    test_config_files: dict,
    construct_beamline_specific: ConstructBeamlineSpecificFeatures,
):
    composite = grid_detect_xrc_devices
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

    # Check backlight was moved IN for grid detect then OUT for gridscan
    backlight_mock = get_mock_put(composite.backlight.position)
    backlight_mock.assert_has_calls(
        [call(InOut.IN, wait=True), call(InOut.OUT, wait=True)],
        any_order=False,
    )
    assert backlight_mock.call_count == 2

    # Check aperture was moved out of beam for grid detect
    assert (
        call(ApertureValue.OUT_OF_BEAM, wait=True)
        in get_mock_put(
            composite.aperture_scatterguard.selected_aperture
        ).call_args_list
    )
    # Check aperture was changed to SMALL
    assert (
        await composite.aperture_scatterguard.selected_aperture.get_value()
        == ApertureValue.SMALL
    )

    # Check we called out to underlying fast grid scan plan
    mock_flyscan.assert_called_once_with(ANY, ANY, ANY)


@patch(
    "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.GridDetectionCallback",
    autospec=True,
)
@patch(
    "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.create_parameters_for_flyscan_xray_centre",
    autospec=True,
)
@patch(
    "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.change_aperture_then_move_to_xtal",
    autospec=True,
)
@patch(
    "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.common_flyscan_xray_centre",
    autospec=True,
)
@patch(
    "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.grid_detection_plan",
    autospec=True,
)
@patch(
    "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.setup_beamline_for_OAV",
    autospec=True,
)
@patch(
    "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.XRayCentreEventHandler",
    autospec=True,
)
def test_detect_grid_and_do_gridscan_sets_up_beamline_for_OAV(
    mock_event_handler: MagicMock,
    mock_setup_beamline_for_oav: MagicMock,
    mock_grid_detect: MagicMock,
    mock_flyscan: MagicMock,
    mock_change_aperture_and_move: MagicMock,
    mock_create_params: MagicMock,
    mock_grid_detect_callback: MagicMock,
    grid_detect_xrc_devices: GridDetectThenXRayCentreComposite,
    sim_run_engine: RunEngineSimulator,
    test_full_grid_scan_params: GridScanWithEdgeDetect,
    test_config_files: dict,
    construct_beamline_specific: ConstructBeamlineSpecificFeatures,
):
    mock_event_handler.return_value.xray_centre_results = ["dummy"]
    sim_run_engine.add_handler_for_callback_subscribes()
    sim_run_engine.simulate_plan(
        grid_detect_then_xray_centre(
            grid_detect_xrc_devices,
            test_full_grid_scan_params,
            construct_beamline_specific=construct_beamline_specific,
            oav_config=test_config_files["oav_config_json"],
            xrc_params_type=SpecifiedThreeDGridScan,
        ),
    )

    mock_setup_beamline_for_oav.assert_called_once()


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
    yield from bps.wait(PlanGroupCheckpointConstants.GRID_READY_FOR_DC)


@pytest.mark.timeout(2)
@patch(
    "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.common_flyscan_xray_centre",
    autospec=True,
)
def test_when_full_grid_scan_run_then_parameters_sent_to_fgs_as_expected(
    mock_flyscan: MagicMock,
    grid_detect_xrc_devices: GridDetectThenXRayCentreComposite,
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
                grid_detect_xrc_devices,
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
    grid_detect_xrc_devices: GridDetectThenXRayCentreComposite,
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
            grid_detect_xrc_devices,
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
    grid_detect_xrc_devices: GridDetectThenXRayCentreComposite,
    test_full_grid_scan_params: GridScanWithEdgeDetect,
    test_config_files: dict[str, str],
    construct_beamline_specific: ConstructBeamlineSpecificFeatures,
):
    mock_grid_detection_plan.return_value = iter(
        [
            Msg("save_oav_grids"),
            Msg(
                "open_run",
                run=DocDescriptorNames.FLYSCAN_RESULTS,
                xray_centre_results=[dataclasses.asdict(FLYSCAN_RESULT_MED)],
            ),
        ]
    )

    sim_run_engine.add_handler_for_callback_subscribes()
    sim_fire_event_on_open_run(sim_run_engine, DocDescriptorNames.FLYSCAN_RESULTS)
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
            grid_detect_xrc_devices,
            test_full_grid_scan_params,
            xrc_params_type=SpecifiedThreeDGridScan,
            construct_beamline_specific=construct_beamline_specific,
            oav_config=test_config_files["oav_config_json"],
        )
    )


def test_grid_detect_then_xray_centre_centres_on_the_first_flyscan_result(
    msgs_from_simulated_grid_detect_then_xray_centre: list[Msg],
):
    assert_message_and_return_remaining(
        msgs_from_simulated_grid_detect_then_xray_centre,
        lambda msg: msg.command == "set"
        and msg.obj.name == "smargon"
        and msg.args[0]
        == CombinedMove(
            x=FLYSCAN_RESULT_MED.centre_of_mass_mm[0],
            y=FLYSCAN_RESULT_MED.centre_of_mass_mm[1],
            z=FLYSCAN_RESULT_MED.centre_of_mass_mm[2],
        ),
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
    "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.detect_grid_and_do_gridscan"
)
@patch(
    "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.XRayCentreEventHandler"
)
@patch(
    "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.change_aperture_then_move_to_xtal"
)
def test_grid_detect_then_xray_centre_plan_moves_beamstop_into_place(
    mock_change_aperture_then_move_to_xtal: MagicMock,
    mock_events_handler: MagicMock,
    mock_grid_detect_then_xray_centre: MagicMock,
    sim_run_engine: RunEngineSimulator,
    grid_detect_xrc_devices: GridDetectThenXRayCentreComposite,
    test_full_grid_scan_params: GridScanWithEdgeDetect,
    construct_beamline_specific: ConstructBeamlineSpecificFeatures,
    test_config_files: dict,
):
    flyscan_event_handler = MagicMock()
    flyscan_event_handler.xray_centre_results = "dummy"
    mock_events_handler.return_value = flyscan_event_handler

    mock_grid_detect_then_xray_centre.return_value = iter(
        [Msg("grid_detect_then_xray_centre")]
    )
    msgs = sim_run_engine.simulate_plan(
        grid_detect_then_xray_centre(
            grid_detect_xrc_devices,
            test_full_grid_scan_params,
            SpecifiedThreeDGridScan,
            construct_beamline_specific,
            test_config_files["oav_config_json"],
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
