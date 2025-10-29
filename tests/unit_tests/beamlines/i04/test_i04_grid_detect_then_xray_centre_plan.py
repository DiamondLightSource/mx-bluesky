from functools import partial
from unittest.mock import ANY, MagicMock, call, patch

import pytest
from bluesky import Msg
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from bluesky.utils import MsgGenerator
from dodal.devices.aperturescatterguard import ApertureScatterguard, ApertureValue
from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
from dodal.devices.backlight import Backlight
from dodal.devices.common_dcm import DoubleCrystalMonochromator
from dodal.devices.detector.detector_motion import DetectorMotion
from dodal.devices.eiger import EigerDetector
from dodal.devices.fast_grid_scan import (
    ZebraFastGridScanThreeD,
)
from dodal.devices.flux import Flux
from dodal.devices.i04.transfocator import Transfocator
from dodal.devices.mx_phase1.beamstop import Beamstop
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.oav.pin_image_recognition import PinTipDetection
from dodal.devices.robot import BartRobot
from dodal.devices.s4_slit_gaps import S4SlitGaps
from dodal.devices.smargon import Smargon
from dodal.devices.synchrotron import Synchrotron
from dodal.devices.undulator import Undulator
from dodal.devices.xbpm_feedback import XBPMFeedback
from dodal.devices.zebra.zebra import Zebra
from dodal.devices.zebra.zebra_controlled_shutter import ZebraShutter
from dodal.devices.zocalo import ZocaloResults
from ophyd_async.testing import set_mock_value

from mx_bluesky.beamlines.i04.experiment_plans.i04_grid_detect_then_xray_centre_plan import (
    DEFAULT_BEAMSIZE_MICRONS,
    get_ready_for_oav_and_close_shutter,
    i04_grid_detect_then_xray_centre,
)
from mx_bluesky.common.parameters.constants import PlanNameConstants
from mx_bluesky.common.parameters.gridscan import GridCommon
from tests.conftest import TEST_RESULT_LARGE, simulate_xrc_result
from tests.unit_tests.common.experiment_plans.test_common_flyscan_xray_centre_plan import (
    CompleteException,
)


class CustomException(Exception): ...


@pytest.fixture
def i04_grid_detect_then_xrc_default_params(
    aperture_scatterguard: ApertureScatterguard,
    attenuator: BinaryFilterAttenuator,
    backlight: Backlight,
    beamstop_phase1: Beamstop,
    dcm: DoubleCrystalMonochromator,
    zebra_fast_grid_scan: ZebraFastGridScanThreeD,
    flux: Flux,
    oav: OAV,
    pin_tip_detection_with_found_pin: PinTipDetection,
    s4_slit_gaps: S4SlitGaps,
    undulator: Undulator,
    xbpm_feedback: XBPMFeedback,
    zebra: Zebra,
    robot: BartRobot,
    sample_shutter: ZebraShutter,
    eiger: EigerDetector,
    synchrotron: Synchrotron,
    zocalo: ZocaloResults,
    smargon: Smargon,
    detector_motion: DetectorMotion,
    test_full_grid_scan_params: GridCommon,
    transfocator: Transfocator,
):
    return partial(
        i04_grid_detect_then_xray_centre,
        parameters=test_full_grid_scan_params,
        aperture_scatterguard=aperture_scatterguard,
        attenuator=attenuator,
        backlight=backlight,
        beamstop=beamstop_phase1,
        dcm=dcm,
        zebra_fast_grid_scan=zebra_fast_grid_scan,
        flux=flux,
        oav=oav,
        pin_tip_detection=pin_tip_detection_with_found_pin,
        s4_slit_gaps=s4_slit_gaps,
        undulator=undulator,
        xbpm_feedback=xbpm_feedback,
        zebra=zebra,
        robot=robot,
        sample_shutter=sample_shutter,
        eiger=eiger,
        synchrotron=synchrotron,
        zocalo=zocalo,
        smargon=smargon,
        detector_motion=detector_motion,
        transfocator=transfocator,
    )


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
    msgs = assert_message_and_return_remaining(
        msgs, predicate=lambda msg: msg.command == "wait"
    )

    msgs = assert_message_and_return_remaining(
        msgs, predicate=lambda msg: msg.command == "setup_beamline_for_oav"
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        predicate=lambda msg: msg.command == "set"
        and msg.obj.name == "detector_motion-shutter"
        and msg.args[0] == 0,
    )
    msgs = assert_message_and_return_remaining(
        msgs, predicate=lambda msg: msg.command == "wait"
    )


@pytest.mark.parametrize(
    "udc",
    [(True), (False)],
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
    i04_grid_detect_then_xrc_default_params: partial[MsgGenerator],
    udc: bool,
):
    RE(
        i04_grid_detect_then_xrc_default_params(
            udc=udc,
        )
    )

    call_count = 0 if udc else 1

    assert mock_get_ready_for_oav_and_close_shutter.call_count == call_count


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
    RE: RunEngine,
    i04_grid_detect_then_xrc_default_params: partial[MsgGenerator],
    transfocator: Transfocator,
):
    mock_common_flyscan_xray_centre.side_effect = CustomException

    with pytest.raises(CustomException):  # noqa: B017
        RE(i04_grid_detect_then_xrc_default_params())

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
    zocalo: ZocaloResults,
    hyperion_fgs_params,
    i04_grid_detect_then_xrc_default_params: partial[MsgGenerator],
):
    flyscan_event_handler = MagicMock()
    flyscan_event_handler.xray_centre_results = "dummy"
    mock_events_handler.return_value = flyscan_event_handler
    mock_create_parameters.return_value = hyperion_fgs_params
    simulate_xrc_result(
        sim_run_engine,
        zocalo,
        TEST_RESULT_LARGE,
    )

    msgs = sim_run_engine.simulate_plan(
        i04_grid_detect_then_xrc_default_params(),
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
    hyperion_fgs_params,
    i04_grid_detect_then_xrc_default_params: partial[MsgGenerator],
):
    mock_create_parameters.return_value = hyperion_fgs_params
    mock_run_gridscan.side_effect = CompleteException
    with pytest.raises(CompleteException):
        RE(i04_grid_detect_then_xrc_default_params())

    mock_verify_gap.assert_called_once()


@patch(
    "mx_bluesky.beamlines.i04.experiment_plans.i04_grid_detect_then_xray_centre_plan.get_ready_for_oav_and_close_shutter",
    autospec=True,
)
@patch(
    "mx_bluesky.beamlines.i04.experiment_plans.i04_grid_detect_then_xray_centre_plan.create_gridscan_callbacks",
    autospec=True,
)
def test_i04_grid_detect_then_xrc_tidies_up_on_exception(
    mock_create_gridscan_callbacks: MagicMock,
    mock_get_ready_for_oav_and_close_shutter: MagicMock,
    RE: RunEngine,
    i04_grid_detect_then_xrc_default_params,
):
    mock_create_gridscan_callbacks.side_effect = CustomException
    with pytest.raises(CustomException):
        RE(
            i04_grid_detect_then_xrc_default_params(
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
async def test_i04_grid_detect_then_xrc_sets_beamsize_before_grid_detect_then_reverts(
    mock_create_gridscan_callbacks: MagicMock,
    mock_setup_beamline_for_oav: MagicMock,
    mock_grid_detect_then_xray_centre: MagicMock,
    mock_get_ready_for_oav_and_close_shutter: MagicMock,
    RE: RunEngine,
    i04_grid_detect_then_xrc_default_params: partial[MsgGenerator],
    transfocator: Transfocator,
    done_status,
):
    initial_beamsize = 5.6
    set_mock_value(transfocator.beamsize_set_microns, initial_beamsize)
    transfocator.set = MagicMock(return_value=done_status)
    parent_mock = MagicMock()
    parent_mock.attach_mock(transfocator.set, "transfocator_set")
    parent_mock.attach_mock(
        mock_create_gridscan_callbacks, "mock_create_gridscan_callbacks"
    )
    RE(i04_grid_detect_then_xrc_default_params())

    assert (
        mock_grid_detect_then_xray_centre.call_args.kwargs[
            "parameters"
        ].selected_aperture
        == ApertureValue.LARGE
    )
    assert parent_mock.method_calls == [
        call.transfocator_set(DEFAULT_BEAMSIZE_MICRONS),
        call.mock_create_gridscan_callbacks(),
        call.transfocator_set(initial_beamsize),
    ]
