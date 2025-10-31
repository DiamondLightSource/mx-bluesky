import asyncio
from contextlib import nullcontext
from unittest.mock import MagicMock, patch

import pytest
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from dodal.beamlines import i03
from dodal.common.beamlines.beamline_parameters import get_beamline_parameters
from dodal.devices.aperturescatterguard import ApertureValue
from dodal.devices.collimation_table import CollimationTable
from dodal.devices.cryostream import CryoStream, CryoStreamGantry, CryoStreamSelection
from dodal.devices.cryostream import InOut as CryoInOut
from dodal.devices.fluorescence_detector_motion import FluorescenceDetector
from dodal.devices.fluorescence_detector_motion import InOut as FlouInOut
from dodal.devices.hutch_shutter import HutchShutter, ShutterDemand, ShutterState
from dodal.devices.ipin import IPinGain
from dodal.devices.mx_phase1.beamstop import Beamstop, BeamstopPositions
from dodal.devices.robot import PinMounted
from dodal.devices.scintillator import InOut, Scintillator
from dodal.devices.xbpm_feedback import Pause
from dodal.devices.zebra.zebra_controlled_shutter import ZebraShutterState
from dodal.testing import patch_all_motors
from ophyd_async.core import Signal, init_devices
from ophyd_async.epics.motor import Motor
from ophyd_async.testing import get_mock_put, set_mock_value

from mx_bluesky.hyperion.experiment_plans.udc_default_state import (
    _PARAM_DATA_COLLECTION_MIN_SAMPLE_CURRENT,
    _PARAM_IPIN_THRESHOLD,
    BeamstopNotInPositionError,
    SampleCurrentBelowThresholdError,
    UDCDefaultDevices,
    UnexpectedSampleError,
    move_beamstop_in_and_verify_using_diode,
    move_to_udc_default_state,
)
from mx_bluesky.hyperion.parameters.constants import HyperionFeatureSetting


@pytest.fixture
async def cryostream_gantry(sim_run_engine: RunEngineSimulator):
    async with init_devices(mock=True):
        cryostream_gantry = CryoStreamGantry("")

    set_mock_value(cryostream_gantry.cryostream_selector, CryoStreamSelection.CRYOJET)
    set_mock_value(cryostream_gantry.cryostream_selected, 1)
    sim_run_engine.add_read_handler_for(
        cryostream_gantry.cryostream_selector, CryoStreamSelection.CRYOJET
    )
    sim_run_engine.add_read_handler_for(cryostream_gantry.cryostream_selected, 1)
    yield cryostream_gantry


@pytest.fixture
async def ipin():
    yield i03.ipin(connect_immediately=True, mock=True)


@pytest.fixture
async def qbpm3():
    yield i03.qbpm3(connect_immediately=True, mock=True)


@pytest.fixture
def beamline_parameters():
    return get_beamline_parameters()


@pytest.fixture
async def default_devices(
    aperture_scatterguard,
    attenuator,
    backlight,
    cryostream_gantry,
    detector_motion,
    ipin,
    qbpm3,
    robot,
    zebra_shutter,
    smargon,
    xbpm_feedback,
    sim_run_engine,
    run_engine,
):
    async def noop(_):
        await asyncio.sleep(0)

    run_engine.register_command("sleep", noop)
    async with init_devices(mock=True):
        cryo = CryoStream("")
        fluo = FluorescenceDetector("")
        beamstop = Beamstop("", MagicMock())
        scintillator = Scintillator("", MagicMock(), MagicMock(), name="scin")
        collimation_table = CollimationTable("")
        hutch_shutter = HutchShutter("")

    with (
        patch_all_motors(scintillator),
        patch_all_motors(collimation_table),
        patch_all_motors(beamstop),
    ):
        devices = UDCDefaultDevices(
            aperture_scatterguard=aperture_scatterguard,
            attenuator=attenuator,
            backlight=backlight,
            beamstop=beamstop,
            collimation_table=collimation_table,
            cryostream=cryo,
            cryostream_gantry=cryostream_gantry,
            detector_motion=detector_motion,
            fluorescence_det_motion=fluo,
            hutch_shutter=hutch_shutter,
            ipin=ipin,
            qbpm3=qbpm3,
            robot=robot,
            sample_shutter=zebra_shutter,
            scintillator=scintillator,
            smargon=smargon,
            xbpm_feedback=xbpm_feedback,
        )
        sim_run_engine.add_read_handler_for(
            devices.sample_shutter, ZebraShutterState.CLOSE
        )
        sim_run_engine.add_handler(
            "locate",
            lambda msg: {"readback": ShutterState.CLOSED},
            "detector_motion-shutter",
        )
        sim_run_engine.add_read_handler_for(devices.ipin.pin_readback, 0.1)
        sim_run_engine.add_read_handler_for(
            devices.robot.gonio_pin_sensor, PinMounted.NO_PIN_MOUNTED
        )

        def put_sample_shutter(value, **kwargs):
            set_mock_value(devices.sample_shutter.position_readback, value)

        get_mock_put(
            devices.sample_shutter._manual_position_setpoint
        ).side_effect = put_sample_shutter
        yield devices


async def test_given_cryostream_temp_is_too_high_then_exception_raised(
    sim_run_engine: RunEngineSimulator,
    default_devices: UDCDefaultDevices,
):
    sim_run_engine.add_read_handler_for(
        default_devices.cryostream.temperature_k,
        default_devices.cryostream.MAX_TEMP_K + 10,
    )
    with pytest.raises(ValueError, match="temperature is too high"):
        sim_run_engine.simulate_plan(move_to_udc_default_state(default_devices))


async def test_given_cryostream_pressure_is_too_high_then_exception_raised(
    sim_run_engine: RunEngineSimulator,
    default_devices: UDCDefaultDevices,
):
    sim_run_engine.add_read_handler_for(
        default_devices.cryostream.back_pressure_bar,
        default_devices.cryostream.MAX_PRESSURE_BAR + 10,
    )
    with pytest.raises(ValueError, match="pressure is too high"):
        sim_run_engine.simulate_plan(move_to_udc_default_state(default_devices))


async def test_scintillator_is_moved_out_before_aperture_scatterguard_moved_in(
    sim_run_engine: RunEngineSimulator,
    default_devices: UDCDefaultDevices,
):
    msgs = sim_run_engine.simulate_plan(move_to_udc_default_state(default_devices))

    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "scin-selected_pos"
        and msg.args[0] == InOut.OUT,
    )
    msgs = assert_message_and_return_remaining(msgs, lambda msg: msg.command == "wait")
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "aperture_scatterguard-selected_aperture"
        and msg.args[0] == ApertureValue.SMALL,
    )


def test_udc_default_state_runs_in_real_run_engine(
    run_engine: RunEngine, default_devices: UDCDefaultDevices
):
    set_mock_value(default_devices.cryostream.temperature_k, 100)
    set_mock_value(default_devices.cryostream.back_pressure_bar, 0.01)
    default_devices.scintillator._aperture_scatterguard().selected_aperture.get_value = MagicMock(
        return_value=ApertureValue.PARKED
    )

    run_engine(move_to_udc_default_state(default_devices))


def test_udc_default_state_group_contains_expected_items_and_is_waited_on(
    sim_run_engine: RunEngineSimulator,
    default_devices: UDCDefaultDevices,
):
    msgs = sim_run_engine.simulate_plan(move_to_udc_default_state(default_devices))

    expected_group = "udc_default"

    def assert_expected_set(signal: Signal | Motor, value):
        return assert_message_and_return_remaining(
            msgs,
            lambda msg: msg.command == "set"
            and msg.obj.name == signal.name
            and msg.args[0] == value
            and msg.kwargs["group"] == expected_group,
        )

    msgs = assert_expected_set(default_devices.hutch_shutter, ShutterDemand.OPEN)

    msgs = assert_expected_set(
        default_devices.fluorescence_det_motion.pos, FlouInOut.OUT
    )
    coll = default_devices.collimation_table
    for device in [
        coll.inboard_y,
        coll.outboard_y,
        coll.upstream_y,
        coll.upstream_x,
        coll.downstream_x,
    ]:
        msgs = assert_expected_set(device, 0)

    # Done as part of beamstop check
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj is default_devices.beamstop.selected_pos
        and msg.args[0] == BeamstopPositions.DATA_COLLECTION,
    )

    msgs = assert_expected_set(
        default_devices.aperture_scatterguard.selected_aperture, ApertureValue.SMALL
    )

    msgs = assert_expected_set(default_devices.cryostream.course, CryoInOut.IN)
    msgs = assert_expected_set(default_devices.cryostream.fine, CryoInOut.IN)

    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "wait" and msg.kwargs["group"] == expected_group,
    )


@pytest.mark.parametrize(
    "expected_raise, cryostream_selection, cryostream_selected",
    [
        [nullcontext(), CryoStreamSelection.CRYOJET, 1],
        [pytest.raises(ValueError), CryoStreamSelection.HC1, 1],
        [pytest.raises(ValueError), CryoStreamSelection.CRYOJET, 0],
    ],
)
def test_udc_default_state_checks_cryostream_selection(
    run_engine: RunEngine,
    default_devices,
    expected_raise,
    cryostream_selection: CryoStreamSelection,
    cryostream_selected: int,
):
    default_devices.scintillator._aperture_scatterguard().selected_aperture.get_value = MagicMock(
        return_value=ApertureValue.PARKED
    )
    set_mock_value(
        default_devices.cryostream_gantry.cryostream_selector, cryostream_selection
    )
    set_mock_value(
        default_devices.cryostream_gantry.cryostream_selected, cryostream_selected
    )

    with expected_raise:
        run_engine(move_to_udc_default_state(default_devices))


def test_beamstop_check_closes_sample_shutter(
    default_devices, sim_run_engine, beamline_parameters
):
    msgs = sim_run_engine.simulate_plan(
        move_beamstop_in_and_verify_using_diode(default_devices, beamline_parameters)
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj is default_devices.sample_shutter
        and msg.args[0] == ZebraShutterState.CLOSE,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "wait"
        and msg.kwargs["group"] == msgs[0].kwargs["group"],
    )


def test_beamstop_check_raises_error_if_sample_current_below_threshold(
    default_devices, sim_run_engine, beamline_parameters
):
    beamline_parameters.params[_PARAM_DATA_COLLECTION_MIN_SAMPLE_CURRENT] = 0.1
    sim_run_engine.add_read_handler_for(default_devices.qbpm3.intensity_uA, 0.099)
    with pytest.raises(SampleCurrentBelowThresholdError):
        sim_run_engine.simulate_plan(
            move_beamstop_in_and_verify_using_diode(
                default_devices, beamline_parameters
            )
        )


def test_beamstop_check_performs_pre_background_check_actions_before_first_background_read(
    default_devices,
    sim_run_engine,
    beamline_parameters,
):
    all_msgs = sim_run_engine.simulate_plan(
        move_beamstop_in_and_verify_using_diode(default_devices, beamline_parameters)
    )
    msgs = assert_message_and_return_remaining(
        all_msgs,
        lambda msg: msg.command == "set"
        and msg.obj is default_devices.backlight
        and msg.args[0] == InOut.OUT,
    )
    pre_check_group = msgs[0].kwargs["group"]
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj is default_devices.xbpm_feedback.pause_feedback
        and msg.args[0] == Pause.RUN,
    )
    feedback_group = msgs[0].kwargs["group"]
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj is default_devices.attenuator
        and msg.args[0] == 1
        and msg.kwargs["group"] == feedback_group,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "wait" and msg.kwargs["group"] == feedback_group,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "trigger"
        and msg.obj is default_devices.xbpm_feedback
        and msg.kwargs["group"] == pre_check_group,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj is default_devices.beamstop.selected_pos
        and msg.args[0] == BeamstopPositions.DATA_COLLECTION
        and msg.kwargs["group"] == pre_check_group,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj is default_devices.ipin.gain
        and msg.args[0] == IPinGain.GAIN_10E4_LOW_NOISE
        and msg.kwargs["group"] == pre_check_group,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj is default_devices.detector_motion.shutter
        and msg.args[0] == ShutterState.CLOSED
        and msg.kwargs["group"] == pre_check_group,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "wait" and msg.kwargs["group"] == pre_check_group,
    )
    msgs = assert_message_and_return_remaining(
        msgs, lambda msg: msg.command == "sleep" and msg.args[0] == 1
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "read"
        and msg.obj is default_devices.ipin.pin_readback,
    )


def test_beamstop_check_completes_post_background_check_actions_before_second_check(
    default_devices, sim_run_engine, beamline_parameters
):
    msgs = sim_run_engine.simulate_plan(
        move_beamstop_in_and_verify_using_diode(default_devices, beamline_parameters)
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj is default_devices.detector_motion.z
        and msg.args[0] == 250,
    )
    post_check_group = msgs[0].kwargs["group"]
    # check background read happens first
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "read"
        and msg.obj is default_devices.ipin.pin_readback,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "wait" and msg.kwargs["group"] == post_check_group,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj is default_devices.sample_shutter
        and msg.args[0] == ZebraShutterState.OPEN,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "wait"
        and msg.kwargs["group"] == msgs[0].kwargs["group"],
    )
    msgs = assert_message_and_return_remaining(
        msgs, lambda msg: msg.command == "sleep" and msg.args[0] == 1
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "read"
        and msg.obj is default_devices.ipin.pin_readback,
    )


def test_beamstop_check_ensures_detector_shutter_closed(
    default_devices, sim_run_engine, beamline_parameters
):
    sim_run_engine.add_handler(
        "locate", lambda msg: {"readback": ShutterState.OPEN}, "detector_motion-shutter"
    )
    with pytest.raises(
        RuntimeError,
        match="Unable to proceed with beamstop background check, shutters did not close",
    ):
        sim_run_engine.simulate_plan(
            move_beamstop_in_and_verify_using_diode(
                default_devices, beamline_parameters
            )
        )


def test_beamstop_check_ensures_sample_shutter_closed(
    default_devices, sim_run_engine, beamline_parameters
):
    sim_run_engine.add_read_handler_for(
        default_devices.sample_shutter, ZebraShutterState.OPEN
    )
    with pytest.raises(
        RuntimeError,
        match="Unable to proceed with beamstop background check, shutters did not close",
    ):
        sim_run_engine.simulate_plan(
            move_beamstop_in_and_verify_using_diode(
                default_devices, beamline_parameters
            )
        )


@pytest.mark.parametrize(
    "ipin_readings, pin_threshold, expected_exception",
    [
        [[0, 0.1], 0.1, None],
        [[0.05, 0.15], 0.1, None],
        [[0, 0.1], 0.099, BeamstopNotInPositionError],
        [[0.05, 0.15], 0.099, BeamstopNotInPositionError],
    ],
)
def test_beamstop_check_checks_background_vs_in_beam_exceeds_threshold(
    ipin_readings,
    pin_threshold,
    expected_exception,
    default_devices,
    sim_run_engine,
    beamline_parameters,
):
    beamline_parameters.params[_PARAM_IPIN_THRESHOLD] = pin_threshold
    it_ipin_readings = iter(ipin_readings)
    sim_run_engine.add_handler(
        "read",
        lambda msg: {"values": {"value": next(it_ipin_readings)}},
        lambda msg: msg.obj is default_devices.ipin.pin_readback,
    )
    with pytest.raises(expected_exception) if expected_exception else nullcontext():
        sim_run_engine.simulate_plan(
            move_beamstop_in_and_verify_using_diode(
                default_devices, beamline_parameters
            )
        )


def test_udc_default_state_checks_that_no_sample_is_present(
    default_devices, sim_run_engine, beamline_parameters
):
    sim_run_engine.add_read_handler_for(default_devices.robot.sample_id, 123456)
    with patch(
        "mx_bluesky.hyperion.experiment_plans.udc_default_state.get_beamline_parameters",
        return_value=beamline_parameters,
    ):
        with pytest.raises(UnexpectedSampleError):
            sim_run_engine.simulate_plan(move_to_udc_default_state(default_devices))


def test_udc_default_state_checks_that_pin_not_mounted(
    default_devices, sim_run_engine, beamline_parameters
):
    sim_run_engine.add_read_handler_for(
        default_devices.robot.gonio_pin_sensor, PinMounted.PIN_MOUNTED
    )
    with patch(
        "mx_bluesky.hyperion.experiment_plans.udc_default_state.get_beamline_parameters",
        return_value=beamline_parameters,
    ):
        with pytest.raises(UnexpectedSampleError):
            sim_run_engine.simulate_plan(move_to_udc_default_state(default_devices))


@pytest.mark.parametrize(
    "current_z, min_z, max_z, expected_move",
    [
        [500, 250, 750, None],
        [0, 250, 750, 250],
        [800, 250, 750, 750],
        [250, 300, 750, 300],
        [720, 250, 680, 680],
    ],
)
def test_beamstop_check_moves_detector_if_outside_thresholds(
    default_devices,
    sim_run_engine,
    beamline_parameters,
    current_z,
    min_z,
    max_z,
    expected_move,
):
    sim_run_engine.add_handler(
        "locate", lambda msg: {"readback": current_z}, "detector_motion-z"
    )
    with patch(
        "mx_bluesky.hyperion.experiment_plans.udc_default_state.get_hyperion_config_client"
    ) as mock_get_config_client:
        mock_get_config_client.return_value.get_feature_flags.return_value = (
            HyperionFeatureSetting(
                DETECTOR_DISTANCE_LIMIT_MAX_MM=max_z,
                DETECTOR_DISTANCE_LIMIT_MIN_MM=min_z,
            )
        )
        msgs = sim_run_engine.simulate_plan(
            move_beamstop_in_and_verify_using_diode(
                default_devices, beamline_parameters
            )
        )

    if expected_move is not None:
        assert_message_and_return_remaining(
            msgs,
            lambda msg: msg.command == "set"
            and msg.obj is default_devices.detector_motion.z
            and msg.args[0] == expected_move,
        )
    else:
        assert (
            len(
                [
                    msg
                    for msg in msgs
                    if msg.command == "set"
                    and msg.obj is default_devices.detector_motion.z
                ]
            )
            == 0
        )
