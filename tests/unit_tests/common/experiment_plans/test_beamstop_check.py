from contextlib import nullcontext
from unittest.mock import MagicMock, patch

import pytest
from bluesky import Msg, RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from dodal.common.beamlines.beamline_parameters import GDABeamlineParameters
from dodal.devices.aperturescatterguard import ApertureValue
from dodal.devices.hutch_shutter import ShutterState
from dodal.devices.ipin import IPinGain
from dodal.devices.mx_phase1.beamstop import BeamstopPositions
from dodal.devices.scintillator import InOut
from dodal.devices.zebra.zebra_controlled_shutter import ZebraShutterState
from ophyd_async.core import set_mock_value, set_mock_values

from mx_bluesky.common.experiment_plans.beamstop_check import (
    _FEEDBACK_TIMEOUT_S,
    _GROUP_POST_BEAMSTOP_OUT_CHECK,
    _GROUP_PRE_BEAMSTOP_OUT_CHECK,
    BeamObstructedError,
    BeamstopCheckDevices,
    BeamstopNotInPositionError,
    SampleCurrentBelowThresholdError,
    _post_beamstop_out_check_actions,
    move_beamstop_in_and_verify_using_diode,
)


def test_beamstop_check_closes_sample_shutter(
    beamstop_check_devices, sim_run_engine, beamline_parameters
):
    msgs = sim_run_engine.simulate_plan(
        move_beamstop_in_and_verify_using_diode(
            beamstop_check_devices,
            beamline_parameters,
            250,
            800,
        )
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj is beamstop_check_devices.sample_shutter
        and msg.args[0] == ZebraShutterState.CLOSE,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "wait"
        and msg.kwargs["group"] == msgs[0].kwargs["group"],
    )


@patch(
    "mx_bluesky.common.experiment_plans.beamstop_check.unpause_xbpm_feedback_and_set_transmission_to_1"
)
def test_beamstop_check_raises_error_if_feedback_fails_to_stabilise(
    mock_unpause_feedback, beamstop_check_devices, run_engine, beamline_parameters
):
    mock_unpause_feedback.side_effect = TimeoutError
    with pytest.raises(SampleCurrentBelowThresholdError):
        run_engine(
            move_beamstop_in_and_verify_using_diode(
                beamstop_check_devices,
                beamline_parameters,
                250,
                800,
            )
        )

    mock_unpause_feedback.assert_called_once_with(
        beamstop_check_devices.xbpm_feedback,
        beamstop_check_devices.attenuator,
        _FEEDBACK_TIMEOUT_S,
    )


@patch(
    "mx_bluesky.common.experiment_plans.beamstop_check.unpause_xbpm_feedback_and_set_transmission_to_1"
)
def test_beamstop_check_performs_pre_beamstop_out_check_actions_before_first_background_read(
    mock_unpause_feedback,
    beamstop_check_devices: BeamstopCheckDevices,
    sim_run_engine,
    beamline_parameters,
):
    """Check that:
    * sample shutter closed
    * feedback unpaused, xmission 100%
    * ap-sg move to out
    * ipin gain set
    * detector shutter closed
    * beamstop out
    * All the above are complete
    Also check that
    * detector move to in range started"""

    mock_unpause_feedback.return_value = iter([Msg("unpause_feedback")])
    all_msgs = sim_run_engine.simulate_plan(
        move_beamstop_in_and_verify_using_diode(
            beamstop_check_devices,
            beamline_parameters,
            250,
            800,
        )
    )

    # Feedback + Transmission
    msgs = assert_message_and_return_remaining(
        all_msgs, lambda msg: msg.command == "unpause_feedback"
    )

    # Pre-beamstop out checks
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj is beamstop_check_devices.backlight
        and msg.args[0] == InOut.OUT,
    )
    pre_check_group = msgs[0].kwargs["group"]
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj is beamstop_check_devices.aperture_scatterguard.selected_aperture
        and msg.args[0] == ApertureValue.OUT_OF_BEAM
        and msg.kwargs["group"] == pre_check_group,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj is beamstop_check_devices.ipin.gain
        and msg.args[0] == IPinGain.GAIN_10E4_LOW_NOISE
        and msg.kwargs["group"] == pre_check_group,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj is beamstop_check_devices.detector_motion.shutter
        and msg.args[0] == ShutterState.CLOSED
        and msg.kwargs["group"] == pre_check_group,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj is beamstop_check_devices.beamstop.selected_pos
        and msg.args[0] == BeamstopPositions.OUT_OF_BEAM
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
        and msg.obj is beamstop_check_devices.ipin.pin_readback,
    )


def test_beamstop_check_completes_post_beamstop_out_check_actions_before_second_check(
    beamstop_check_devices, sim_run_engine, beamline_parameters
):
    msgs = sim_run_engine.simulate_plan(
        move_beamstop_in_and_verify_using_diode(
            beamstop_check_devices,
            beamline_parameters,
            250,
            800,
        )
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj is beamstop_check_devices.detector_motion.z
        and msg.args[0] == 250,
    )
    post_check_group = msgs[0].kwargs["group"]
    # check background read happens first
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "read"
        and msg.obj is beamstop_check_devices.ipin.pin_readback,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "wait" and msg.kwargs["group"] == post_check_group,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj is beamstop_check_devices.sample_shutter
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
        and msg.obj is beamstop_check_devices.ipin.pin_readback,
    )


def test_beamstop_check_ensures_detector_shutter_closed(
    beamstop_check_devices, sim_run_engine, beamline_parameters
):
    sim_run_engine.add_handler(
        "locate", lambda msg: {"readback": ShutterState.OPEN}, "detector_motion-shutter"
    )
    with pytest.raises(
        RuntimeError,
        match="Unable to proceed with beamstop background check, detector shutter did not close",
    ):
        sim_run_engine.simulate_plan(
            move_beamstop_in_and_verify_using_diode(
                beamstop_check_devices,
                beamline_parameters,
                250,
                800,
            )
        )


@pytest.mark.parametrize(
    "ipin_reading_with_beamstop_out, beamstop_threshold, commissioning_mode, expected_exception",
    [
        [0.099, 0.1, False, BeamObstructedError],
        [0.101, 0.1, False, None],
        [0.099, 0.05, False, None],
        [0.099, 0.15, False, BeamObstructedError],
        [0.099, 0.15, True, None],
    ],
)
@patch(
    "mx_bluesky.common.experiment_plans.beamstop_check._post_beamstop_out_check_actions"
)
@patch("mx_bluesky.common.experiment_plans.beamstop_check.bps.sleep", new=MagicMock())
def test_beamstop_check_checks_beamstop_out_diode_above_threshold_before_second_check(
    mock_post_beamstop_out_actions,
    beamstop_check_devices: BeamstopCheckDevices,
    run_engine: RunEngine,
    beamline_parameters: GDABeamlineParameters,
    ipin_reading_with_beamstop_out,
    beamstop_threshold: float,
    commissioning_mode: bool,
    expected_exception: Exception | None,
):
    set_mock_value(beamstop_check_devices.baton.commissioning, commissioning_mode)
    beamline_parameters.params["ipin_threshold"] = beamstop_threshold
    value_iter = set_mock_values(
        beamstop_check_devices.ipin.pin_readback, [ipin_reading_with_beamstop_out, 0]
    )
    next(value_iter)

    def bump_reading_iter_on_post_bs_actions(*args, **kwargs):
        next(value_iter)
        yield from _post_beamstop_out_check_actions(*args, **kwargs)

    mock_post_beamstop_out_actions.side_effect = bump_reading_iter_on_post_bs_actions

    with pytest.raises(expected_exception) if expected_exception else nullcontext():
        run_engine(
            move_beamstop_in_and_verify_using_diode(
                beamstop_check_devices,
                beamline_parameters,
                250,
                800,
            )
        )


@pytest.mark.parametrize(
    "ipin_reading_with_beamstop_in, beamstop_threshold, expected_exception",
    [
        [0.101, 0.1, BeamstopNotInPositionError],
        [0.099, 0.1, None],
        [0.051, 0.05, BeamstopNotInPositionError],
        [0.149, 0.15, None],
    ],
)
@patch(
    "mx_bluesky.common.experiment_plans.beamstop_check._post_beamstop_out_check_actions"
)
@patch("mx_bluesky.common.experiment_plans.beamstop_check.bps.sleep", new=MagicMock())
def test_beamstop_check_checks_beamstop_in_diode_below_threshold(
    mock_post_beamstop_out_actions,
    beamstop_check_devices: BeamstopCheckDevices,
    run_engine: RunEngine,
    beamline_parameters: GDABeamlineParameters,
    ipin_reading_with_beamstop_in,
    beamstop_threshold: float,
    expected_exception: Exception | None,
):
    beamline_parameters.params["ipin_threshold"] = beamstop_threshold
    value_iter = set_mock_values(
        beamstop_check_devices.ipin.pin_readback, [100, ipin_reading_with_beamstop_in]
    )
    next(value_iter)

    def bump_reading_iter_on_post_bs_actions(*args, **kwargs):
        next(value_iter)
        yield from _post_beamstop_out_check_actions(*args, **kwargs)

    mock_post_beamstop_out_actions.side_effect = bump_reading_iter_on_post_bs_actions

    with pytest.raises(expected_exception) if expected_exception else nullcontext():
        run_engine(
            move_beamstop_in_and_verify_using_diode(
                beamstop_check_devices,
                beamline_parameters,
                250,
                800,
            )
        )


def test_beamstop_check_operates_shutter_and_beamstop_during_ipin_check(
    sim_run_engine: RunEngineSimulator,
    beamstop_check_devices: BeamstopCheckDevices,
    beamline_parameters: GDABeamlineParameters,
):
    msgs = sim_run_engine.simulate_plan(
        move_beamstop_in_and_verify_using_diode(
            beamstop_check_devices,
            beamline_parameters,
            250,
            800,
        )
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "wait"
        and msg.kwargs["group"] == _GROUP_PRE_BEAMSTOP_OUT_CHECK,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj is beamstop_check_devices.sample_shutter
        and msg.args[0] == ZebraShutterState.OPEN,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "read"
        and msg.obj is beamstop_check_devices.ipin.pin_readback,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj is beamstop_check_devices.sample_shutter
        and msg.args[0] == ZebraShutterState.CLOSE,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj is beamstop_check_devices.beamstop.selected_pos
        and msg.args[0] == BeamstopPositions.DATA_COLLECTION
        and msg.kwargs["group"] == _GROUP_POST_BEAMSTOP_OUT_CHECK,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "wait"
        and msg.kwargs["group"] == _GROUP_POST_BEAMSTOP_OUT_CHECK,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj is beamstop_check_devices.sample_shutter
        and msg.args[0] == ZebraShutterState.OPEN,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "read"
        and msg.obj is beamstop_check_devices.ipin.pin_readback,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj is beamstop_check_devices.sample_shutter
        and msg.args[0] == ZebraShutterState.CLOSE,
    )


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
    beamstop_check_devices,
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
    msgs = sim_run_engine.simulate_plan(
        move_beamstop_in_and_verify_using_diode(
            beamstop_check_devices,
            beamline_parameters,
            min_z,
            max_z,
        )
    )

    if expected_move is not None:
        assert_message_and_return_remaining(
            msgs,
            lambda msg: msg.command == "set"
            and msg.obj is beamstop_check_devices.detector_motion.z
            and msg.args[0] == expected_move,
        )
    else:
        assert (
            len(
                [
                    msg
                    for msg in msgs
                    if msg.command == "set"
                    and msg.obj is beamstop_check_devices.detector_motion.z
                ]
            )
            == 0
        )
