import dataclasses
from unittest.mock import ANY, MagicMock, call, patch

import bluesky.plan_stubs as bps
import pytest
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from bluesky.utils import Msg
from daq_config_server import ConfigClient
from dodal.devices.aperturescatterguard import ApertureValue
from dodal.devices.backlight import InOut
from dodal.devices.eiger import FREE_RUN_MAX_IMAGES
from dodal.devices.mx_phase1.beamstop import BeamstopPositions
from dodal.devices.oav.oav_parameters import OAVParameters
from dodal.devices.oav.pin_image_recognition import PinTipDetection
from ophyd_async.core import get_mock_put

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
from mx_bluesky.common.external_interaction.callbacks.grid.grid_detect_and_scan.ispyb_callback import (
    ispyb_activation_wrapper,
)
from mx_bluesky.common.parameters.components import DiffractionExperimentWithSample
from mx_bluesky.common.parameters.constants import (
    DocDescriptorNames,
    PlanGroupCheckpointConstants,
)
from mx_bluesky.common.parameters.device_composites import (
    GridDetectAndGridScanEssentialDevices,
)
from mx_bluesky.common.parameters.gridscan import (
    GridDetectionParams,
    GridScanParams,
    create_detector_params_for_grid_scan,
    fast_gridscan_params,
)
from mx_bluesky.hyperion.parameters.device_composites import (
    GridDetectThenXRayCentreComposite,
)

from ....conftest import (
    ConfigFilesForTests,
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
    return lambda xrc_composite, xrc_parameters, grid_scan_params: beamline_specific


@pytest.mark.timeout(2)
@patch(
    "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.common_flyscan_xray_centre",
    autospec=True,
)
async def test_detect_grid_and_do_gridscan_in_real_run_engine(
    mock_flyscan: MagicMock,
    pin_tip_detection_with_found_pin: PinTipDetection,
    grid_detect_xrc_devices: GridDetectThenXRayCentreComposite,
    run_engine: RunEngine,
    minimal_diffraction_expt_with_sample: DiffractionExperimentWithSample,
    grid_detect_params: GridDetectionParams,
    test_config_files: ConfigFilesForTests,
    construct_beamline_specific: ConstructBeamlineSpecificFeatures,
):
    composite = grid_detect_xrc_devices
    run_engine(
        ispyb_activation_wrapper(
            _do_detect_grid_and_gridscan_then_wait_for_backlight(
                composite,
                test_config_files,
                minimal_diffraction_expt_with_sample,
                grid_detect_params,
                construct_beamline_specific,
            ),
            minimal_diffraction_expt_with_sample,
            create_detector_params_for_grid_scan(minimal_diffraction_expt_with_sample),
        )
    )

    # Check backlight was moved IN for grid detect then OUT for gridscan
    backlight_mock = get_mock_put(composite.backlight.position)
    backlight_mock.assert_has_calls(
        [call(InOut.IN), call(InOut.OUT)],
        any_order=False,
    )
    assert backlight_mock.call_count == 2

    # Check aperture was moved out of beam for grid detect
    assert (
        call(ApertureValue.OUT_OF_BEAM)
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
    mock_flyscan.assert_called_once_with(ANY, ANY, ANY, ANY, ANY)


@patch(
    "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.GridDetectionCallback",
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
    "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.setup_beamline_for_oav",
    autospec=True,
)
def test_detect_grid_and_do_gridscan_sets_up_beamline_for_oav(
    mock_setup_beamline_for_oav: MagicMock,
    mock_grid_detect: MagicMock,
    mock_flyscan: MagicMock,
    mock_grid_detect_callback: MagicMock,
    grid_detect_xrc_devices: GridDetectThenXRayCentreComposite,
    sim_run_engine: RunEngineSimulator,
    minimal_diffraction_expt_with_sample: DiffractionExperimentWithSample,
    grid_detect_params: GridDetectionParams,
    test_config_files: dict,
    construct_beamline_specific: ConstructBeamlineSpecificFeatures,
):
    mock_grid_detect_callback.return_value.get_grid_parameters.return_value = {
        "x_start_um": 0,
        "y_starts_um": [0, 0],
        "z_starts_um": [0, 0],
        "x_steps": 10,
        "y_steps": [10, 10],
        "x_step_size_um": 10,
        "y_step_sizes_um": [10, 10],
    }
    sim_run_engine.add_handler_for_callback_subscribes()
    sim_run_engine.simulate_plan(
        grid_detect_then_xray_centre(
            grid_detect_xrc_devices,
            minimal_diffraction_expt_with_sample,
            grid_detect_params,
            create_detector_params_for_grid_scan(minimal_diffraction_expt_with_sample),
            construct_beamline_specific=construct_beamline_specific,
            oav_config=test_config_files["oav_config_json"],
        ),
    )
    mock_setup_beamline_for_oav.assert_called_once()


def _do_detect_grid_and_gridscan_then_wait_for_backlight(
    composite: GridDetectAndGridScanEssentialDevices,
    test_config_files: ConfigFilesForTests,
    expt_params: DiffractionExperimentWithSample,
    grid_detection_params: GridDetectionParams,
    construct_beamline_specific_xrc_features,
):
    yield from detect_grid_and_do_gridscan(
        composite,
        parameters=expt_params,
        grid_detection_params=grid_detection_params,
        oav_params=OAVParameters(
            ConfigClient(""), "xrayCentring", test_config_files["oav_config_json"]
        ),
        detector_params=create_detector_params_for_grid_scan(expt_params),
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
    run_engine: RunEngine,
    minimal_diffraction_expt_with_sample: DiffractionExperimentWithSample,
    grid_detect_params: GridDetectionParams,
    test_config_files: dict,
    pin_tip_detection_with_found_pin: PinTipDetection,
    construct_beamline_specific: ConstructBeamlineSpecificFeatures,
):
    oav_params = OAVParameters(
        ConfigClient(""), "xrayCentring", test_config_files["oav_config_json"]
    )

    detector_params = create_detector_params_for_grid_scan(
        minimal_diffraction_expt_with_sample
    )
    run_engine(
        ispyb_activation_wrapper(
            detect_grid_and_do_gridscan(
                grid_detect_xrc_devices,
                parameters=minimal_diffraction_expt_with_sample,
                grid_detection_params=grid_detect_params,
                oav_params=oav_params,
                detector_params=detector_params,
                construct_beamline_specific=construct_beamline_specific,
            ),
            minimal_diffraction_expt_with_sample,
            detector_params,
        )
    )

    params: DiffractionExperimentWithSample = mock_flyscan.call_args[0][1]
    actual_detector_params = mock_flyscan.call_args[0][2]
    grid_scan_params: GridScanParams = mock_flyscan.call_args[0][3]
    assert actual_detector_params.num_triggers == FREE_RUN_MAX_IMAGES
    fgs_params = fast_gridscan_params(params, grid_scan_params)
    assert fgs_params.x_axis.full_steps == 15
    assert fgs_params.y_axis.end == pytest.approx(-0.06329, 0.001)

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
    minimal_diffraction_expt_with_sample: DiffractionExperimentWithSample,
    grid_detect_params: GridDetectionParams,
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
            minimal_diffraction_expt_with_sample,
            grid_detect_params,
            OAVParameters(
                ConfigClient(""), "xrayCentring", test_config_files["oav_config_json"]
            ),
            detector_params=create_detector_params_for_grid_scan(
                minimal_diffraction_expt_with_sample
            ),
            construct_beamline_specific=construct_beamline_specific,
        )
    )

    activations = [
        msg
        for msg in msgs
        if msg.command == "open_run"
        and "GridDetectAndScanISPyBCallback" in msg.kwargs["activate_callbacks"]
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
    minimal_diffraction_expt_with_sample: DiffractionExperimentWithSample,
    grid_detect_params: GridDetectionParams,
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
            minimal_diffraction_expt_with_sample,
            grid_detect_params,
            detector_params=create_detector_params_for_grid_scan(
                minimal_diffraction_expt_with_sample
            ),
            construct_beamline_specific=construct_beamline_specific,
            oav_config=test_config_files["oav_config_json"],
        )
    )


def test_grid_detect_then_xray_centre_activates_ispyb_callback(
    msgs_from_simulated_grid_detect_then_xray_centre: list[Msg],
):
    assert_message_and_return_remaining(
        msgs_from_simulated_grid_detect_then_xray_centre,
        lambda msg: (
            msg.command == "open_run"
            and "GridDetectAndScanISPyBCallback" in msg.kwargs["activate_callbacks"]
        ),
    )


def test_detect_grid_and_do_gridscan_waits_for_aperture_to_be_prepared_before_moving_in(
    msgs_from_simulated_grid_detect_then_xray_centre: list[Msg],
):
    msgs = assert_message_and_return_remaining(
        msgs_from_simulated_grid_detect_then_xray_centre,
        lambda msg: (
            msg.command == "prepare"
            and msg.obj.name == "aperture_scatterguard"
            and msg.args[0] == ApertureValue.SMALL
        ),
    )

    aperture_prepare_group = msgs[0].kwargs.get("group")

    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: (
            msg.command == "wait" and msg.kwargs["group"] == aperture_prepare_group
        ),
    )

    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: (
            msg.command == "set"
            and msg.obj.name == "aperture_scatterguard-selected_aperture"
            and msg.args[0] == ApertureValue.SMALL
        ),
    )


@patch(
    "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.detect_grid_and_do_gridscan"
)
def test_grid_detect_then_xray_centre_plan_moves_beamstop_into_place(
    mock_grid_detect_then_xray_centre: MagicMock,
    sim_run_engine: RunEngineSimulator,
    grid_detect_xrc_devices: GridDetectThenXRayCentreComposite,
    minimal_diffraction_expt_with_sample: DiffractionExperimentWithSample,
    grid_detect_params: GridDetectionParams,
    construct_beamline_specific: ConstructBeamlineSpecificFeatures,
    test_config_files: dict,
):
    def mock_grid_detect_then_xrc_plan(*args, **kwargs):
        yield Msg("grid_detect_then_xray_centre")
        return GridScanParams(
            omega_starts_deg=[0, 90],
            x_steps=10,
            y_steps=[10, 10],
            x_start_um=0,
            y_starts_um=[0, 0],
            z_starts_um=[0, 0],
            x_step_size_um=10,
            y_step_sizes_um=[10, 10],
        )

    mock_grid_detect_then_xray_centre.side_effect = mock_grid_detect_then_xrc_plan

    msgs = sim_run_engine.simulate_plan(
        grid_detect_then_xray_centre(
            grid_detect_xrc_devices,
            minimal_diffraction_expt_with_sample,
            grid_detect_params,
            create_detector_params_for_grid_scan(minimal_diffraction_expt_with_sample),
            construct_beamline_specific,
            test_config_files["oav_config_json"],
        )
    )

    msgs = assert_message_and_return_remaining(
        msgs,
        predicate=lambda msg: (
            msg.command == "set"
            and msg.obj.name == "beamstop-selected_pos"
            and msg.args[0] == BeamstopPositions.DATA_COLLECTION
        ),
    )

    msgs = assert_message_and_return_remaining(
        msgs, predicate=lambda msg: msg.command == "grid_detect_then_xray_centre"
    )
