from collections.abc import Generator
from typing import cast
from unittest.mock import ANY, MagicMock, call, patch

import pytest
from bluesky import Msg
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from dodal.devices.aperturescatterguard import ApertureValue
from dodal.devices.backlight import BacklightPosition
from dodal.devices.oav.pin_image_recognition import PinTipDetection
from tests.conftest import TEST_RESULT_LARGE, simulate_xrc_result
from tests.unit_tests.common.experiment_plans.test_common_flyscan_xray_centre_plan import (
    CompleteException,
)

from mx_bluesky.beamlines.i04.experiment_plans.i04_grid_detect_then_xray_centre_plan import (
    get_ready_for_oav_and_close_shutter,
    i04_grid_detect_then_xray_centre,
)
from mx_bluesky.common.parameters.constants import PlanNameConstants
from mx_bluesky.common.parameters.device_composites import (
    GridDetectThenXRayCentreComposite,
)
from mx_bluesky.common.parameters.gridscan import GridCommon
from mx_bluesky.hyperion.parameters.device_composites import (
    HyperionGridDetectThenXRayCentreComposite,
)
from mx_bluesky.hyperion.parameters.gridscan import (
    GridScanWithEdgeDetect,
    HyperionSpecifiedThreeDGridScan,
)


def test_full_i04_grid_scan(
    hyperion_fgs_params: HyperionSpecifiedThreeDGridScan,
    test_config_files: dict[str, str],
):
    devices = MagicMock()
    plan = i04_grid_detect_then_xray_centre(
        devices,
        cast(GridScanWithEdgeDetect, hyperion_fgs_params),
        test_config_files["oav_config_json"],
    )
    assert isinstance(plan, Generator)


@patch(
    "mx_bluesky.beamlines.i04.experiment_plans.i04_grid_detect_then_xray_centre_plan.setup_beamline_for_OAV",
    autospec=True,
)
def test_get_ready_for_oav_and_close_shutter_closes_shutter_and_calls_setup_for_oav_plan(
    mock_setup_beamline_for_oav: MagicMock,
    sim_run_engine: RunEngineSimulator,
    grid_detect_xrc_devices,
):
    mock_setup_beamline_for_oav.return_value = iter([Msg("setup_beamline_for_oav")])

    msgs = sim_run_engine.simulate_plan(
        get_ready_for_oav_and_close_shutter(
            grid_detect_xrc_devices.smargon,
            grid_detect_xrc_devices.backlight,
            grid_detect_xrc_devices.aperture_scatterguard,
            grid_detect_xrc_devices.detector_motion,
        )
    )
    for msg in msgs:
        print(msg)
    msgs = assert_message_and_return_remaining(
        msgs, predicate=lambda msg: msg.command == "setup_beamline_for_oav"
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        predicate=lambda msg: msg.command == "set"
        and msg.obj.name == "detector_motion-shutter"
        and msg.args[0] == 0,
    )


@patch(
    "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.grid_detection_plan",
    autospec=True,
)
@patch(
    "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.move_aperture_if_required",
    autospec=True,
)
@patch(
    "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.create_parameters_for_flyscan_xray_centre",
    autospec=True,
)
@patch(
    "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.GridDetectionCallback",
    autospec=True,
)
@patch(
    "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.XRayCentreEventHandler",
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
def test_i04_grid_detect_then_xrc_sets_up_beamline_for_oav_before_grid_detect(
    mock_common_flyscan_xray_center: MagicMock,
    mock_change_aperture_then_move_to_xtal: MagicMock,
    mock_xray_centre_event_handler: MagicMock,
    mock_grid_detection_callback: MagicMock,
    mock_create_parameters_for_flyscan_xray_centre: MagicMock,
    mock_move_aperture_if_required: MagicMock,
    mock_grid_detection_plan: MagicMock,
    sim_run_engine: RunEngineSimulator,
    grid_detect_xrc_devices: GridDetectThenXRayCentreComposite,
    test_full_grid_scan_params: GridCommon,
    test_config_files,
):
    flyscan_event_handler = MagicMock()
    flyscan_event_handler.xray_centre_results = "dummy"
    mock_xray_centre_event_handler.return_value = flyscan_event_handler

    mock_grid_detection_plan.return_value = iter([Msg("grid_detection_plan")])

    msgs = sim_run_engine.simulate_plan(
        i04_grid_detect_then_xray_centre(
            grid_detect_xrc_devices,
            test_full_grid_scan_params,
            oav_config=test_config_files["oav_config_json"],
        ),
    )
    # backlight should move in
    msgs = assert_message_and_return_remaining(
        msgs,
        predicate=lambda msg: msg.command == "set"
        and msg.obj.name == "backlight"
        and msg.args[0] == BacklightPosition.IN,
    )
    # aperture should move out
    msgs = assert_message_and_return_remaining(
        msgs,
        predicate=lambda msg: msg.command == "set"
        and msg.obj.name == "aperture_scatterguard-selected_aperture"
        and msg.args[0] == ApertureValue.OUT_OF_BEAM,
    )

    msgs = assert_message_and_return_remaining(
        msgs, predicate=lambda msg: msg.command == "grid_detection_plan"
    )


@patch(
    "mx_bluesky.beamlines.i04.experiment_plans.i04_grid_detect_then_xray_centre_plan.get_ready_for_oav_and_close_shutter",
    autospec=True,
)
@patch(
    "mx_bluesky.beamlines.i04.experiment_plans.i04_grid_detect_then_xray_centre_plan.grid_detect_then_xray_centre",
    autospec=True,
)
@patch(
    "mx_bluesky.beamlines.i04.experiment_plans.i04_grid_detect_then_xray_centre_plan.setup_beamline_for_OAV",
    autospec=True,
)
@patch(
    "mx_bluesky.beamlines.i04.experiment_plans.i04_grid_detect_then_xray_centre_plan.create_gridscan_callbacks",
    autospec=True,
)
def test_i04_grid_detect_then_xrc_closes_shutter_and_tidies_if_not_udc(
    mock_create_gridscan_callbacks: MagicMock,
    mock_setup_beamline_for_oav: MagicMock,
    mock_grid_detect_then_xray_centre: MagicMock,
    mock_get_ready_for_oav_and_close_shutter: MagicMock,
    RE: RunEngine,
    grid_detect_xrc_devices: GridDetectThenXRayCentreComposite,
    test_full_grid_scan_params: GridCommon,
    test_config_files,
):
    RE(
        i04_grid_detect_then_xray_centre(
            grid_detect_xrc_devices,
            test_full_grid_scan_params,
            test_config_files["oav_config_json"],
            udc=False,
        )
    )

    assert mock_get_ready_for_oav_and_close_shutter.call_count == 1


@patch(
    "mx_bluesky.beamlines.i04.experiment_plans.i04_grid_detect_then_xray_centre_plan.get_ready_for_oav_and_close_shutter",
    autospec=True,
)
@patch(
    "mx_bluesky.beamlines.i04.experiment_plans.i04_grid_detect_then_xray_centre_plan.grid_detect_then_xray_centre",
    autospec=True,
)
@patch(
    "mx_bluesky.beamlines.i04.experiment_plans.i04_grid_detect_then_xray_centre_plan.setup_beamline_for_OAV",
    autospec=True,
)
@patch(
    "mx_bluesky.beamlines.i04.experiment_plans.i04_grid_detect_then_xray_centre_plan.create_gridscan_callbacks",
    autospec=True,
)
def test_i04_grid_detect_then_xrc_does_not_close_shutter_and_tidy_if_udc(
    mock_create_gridscan_callbacks: MagicMock,
    mock_setup_beamline_for_oav: MagicMock,
    mock_grid_detect_then_xray_centre: MagicMock,
    mock_get_ready_for_oav_and_close_shutter: MagicMock,
    RE: RunEngine,
    grid_detect_xrc_devices: GridDetectThenXRayCentreComposite,
    test_full_grid_scan_params: GridCommon,
    test_config_files,
):
    RE(
        i04_grid_detect_then_xray_centre(
            grid_detect_xrc_devices,
            test_full_grid_scan_params,
            test_config_files["oav_config_json"],
            udc=True,
        )
    )

    assert mock_get_ready_for_oav_and_close_shutter.call_count == 0


@patch(
    "mx_bluesky.beamlines.i04.experiment_plans.i04_grid_detect_then_xray_centre_plan.create_gridscan_callbacks",
    autospec=True,
)
@patch(
    "mx_bluesky.common.preprocessors.preprocessors.check_and_pause_feedback",
    autospec=True,
)
@patch(
    "mx_bluesky.common.preprocessors.preprocessors.unpause_xbpm_feedback_and_set_transmission_to_1",
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
    "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.create_parameters_for_flyscan_xray_centre",
    autospec=True,
)
@patch(
    "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.GridDetectionCallback",
    autospec=True,
)
@patch("bluesky.plan_stubs.sleep", autospec=True)
def test_i04_xray_centre_unpauses_xbpm_feedback_on_exception(
    mock_sleep: MagicMock,
    mock_grid_detection_callback: MagicMock,
    mock_create_parameters_for_flyscan_xray_centre: MagicMock,
    mock_grid_detection_plan: MagicMock,
    mock_common_flyscan_xray_centre: MagicMock,
    mock_unpause_and_set_transmission: MagicMock,
    mock_check_and_pause: MagicMock,
    mock_create_gridscan_callbacks: MagicMock,
    grid_detect_xrc_devices: HyperionGridDetectThenXRayCentreComposite,
    test_full_grid_scan_params: GridScanWithEdgeDetect,
    test_config_files,
    pin_tip_detection_with_found_pin: PinTipDetection,
    RE: RunEngine,
):
    class TestException(Exception): ...

    mock_common_flyscan_xray_centre.side_effect = TestException

    with pytest.raises(TestException):  # noqa: B017
        RE(
            i04_grid_detect_then_xray_centre(
                grid_detect_xrc_devices,
                test_full_grid_scan_params,
                test_config_files["oav_config_json"],
            )
        )

    # Called once on exception and once on close_run
    mock_unpause_and_set_transmission.assert_has_calls([call(ANY, ANY)])


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
@patch(
    "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.XRayCentreEventHandler"
)
@patch(
    "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.change_aperture_then_move_to_xtal"
)
def test_i04_grid_detect_then_xray_centre_pauses_and_unpauses_xbpm_feedback_in_correct_order(
    mock_change_aperture_then_move: MagicMock,
    mock_events_handler: MagicMock,
    mock_create_parameters: MagicMock,
    mock_grid_detection_callback: MagicMock,
    mock_grid_detection_plan: MagicMock,
    mock_check_topup: MagicMock,
    mock_wait: MagicMock,
    sim_run_engine: RunEngineSimulator,
    test_full_grid_scan_params: GridScanWithEdgeDetect,
    grid_detect_xrc_devices: HyperionGridDetectThenXRayCentreComposite,
    test_config_files,
    hyperion_fgs_params,
):
    flyscan_event_handler = MagicMock()
    flyscan_event_handler.xray_centre_results = "dummy"
    mock_events_handler.return_value = flyscan_event_handler
    mock_create_parameters.return_value = hyperion_fgs_params
    simulate_xrc_result(
        sim_run_engine,
        grid_detect_xrc_devices.zocalo,
        TEST_RESULT_LARGE,
    )

    msgs = sim_run_engine.simulate_plan(
        i04_grid_detect_then_xray_centre(
            grid_detect_xrc_devices,
            test_full_grid_scan_params,
            test_config_files["oav_config_json"],
        ),
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


@patch(
    "mx_bluesky.beamlines.i04.experiment_plans.i04_grid_detect_then_xray_centre_plan.create_gridscan_callbacks",
    autospec=True,
)
@patch(
    "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.grid_detection_plan",
)
@patch(
    "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.move_aperture_if_required",
)
@patch(
    "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.GridDetectionCallback",
)
@patch(
    "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.create_parameters_for_flyscan_xray_centre",
)
@patch(
    "mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan.run_gridscan",
)
@patch(
    "mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan._fetch_xrc_results_from_zocalo",
)
@patch(
    "dodal.plans.preprocessors.verify_undulator_gap.verify_undulator_gap",
)
def test_i04_grid_detect_then_xray_centre_does_undulator_check_before_collection(
    mock_verify_gap: MagicMock,
    mock_fetch_zocalo_results: MagicMock,
    mock_run_gridscan: MagicMock,
    mock_create_parameters: MagicMock,
    mock_grid_params_callback: MagicMock,
    mock_move_aperture_if_required: MagicMock,
    mock_grid_detection_plan: MagicMock,
    mock_create_gridscan_callbacks: MagicMock,
    RE: RunEngine,
    test_full_grid_scan_params: GridScanWithEdgeDetect,
    grid_detect_xrc_devices: HyperionGridDetectThenXRayCentreComposite,
    test_config_files,
    hyperion_fgs_params,
):
    mock_create_parameters.return_value = hyperion_fgs_params
    mock_run_gridscan.side_effect = CompleteException
    with pytest.raises(CompleteException):
        RE(
            i04_grid_detect_then_xray_centre(
                grid_detect_xrc_devices,
                test_full_grid_scan_params,
                test_config_files["oav_config_json"],
            )
        )

    mock_verify_gap.assert_called_once()
