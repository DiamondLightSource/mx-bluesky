from unittest.mock import MagicMock, call, patch

import pytest
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
from dodal.devices.backlight import Backlight
from dodal.devices.i04.max_pixel import MaxPixel
from dodal.devices.mx_phase1.beamstop import Beamstop, BeamstopPositions
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.robot import BartRobot, PinMounted
from dodal.devices.scintillator import InOut, Scintillator
from dodal.devices.xbpm_feedback import XBPMFeedback
from dodal.devices.zebra.zebra_controlled_shutter import (
    ZebraShutter,
    ZebraShutterControl,
    ZebraShutterState,
)
from ophyd_async.core import completed_status, init_devices, set_mock_value

from mx_bluesky.beamlines.i04.oav_centering_plans.oav_imaging import (
    _prepare_beamline_for_scintillator_images,
    optimise_transmission_with_oav,
    take_and_save_oav_image,
    take_oav_image_with_scintillator_in,
)
from mx_bluesky.common.utils.exceptions import BeamlineStateError


async def test_check_exception_raised_if_pin_mounted(
    run_engine: RunEngine,
    robot: BartRobot,
    beamstop_phase1: Beamstop,
    scintillator: Scintillator,
    attenuator: BinaryFilterAttenuator,
    sample_shutter: ZebraShutter,
    oav: OAV,
):
    set_mock_value(robot.gonio_pin_sensor, PinMounted.PIN_MOUNTED)

    with pytest.raises(BeamlineStateError, match="Pin should not be mounted!"):
        run_engine(
            take_oav_image_with_scintillator_in(
                robot=robot,
                beamstop=beamstop_phase1,
                scintillator=scintillator,
                attenuator=attenuator,
                shutter=sample_shutter,
                oav=oav,
            )
        )


def test_prepare_beamline_for_scint_images(
    sim_run_engine: RunEngineSimulator,
    robot: BartRobot,
    beamstop_phase1: Beamstop,
    backlight: Backlight,
    scintillator: Scintillator,
    xbpm_feedback: XBPMFeedback,
    sample_shutter: ZebraShutter,
):
    test_group = "my_group"
    messages = sim_run_engine.simulate_plan(
        _prepare_beamline_for_scintillator_images(
            robot,
            beamstop_phase1,
            backlight,
            scintillator,
            xbpm_feedback,
            sample_shutter,
            test_group,
        )
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "read" and msg.obj.name == "robot-gonio_pin_sensor",
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "trigger" and msg.obj.name == "xbpm_feedback",
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "set"
        and msg.obj.name == "beamstop-selected_pos"
        and msg.args[0] == BeamstopPositions.DATA_COLLECTION
        and msg.kwargs["group"] == test_group,
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "set"
        and msg.obj.name == "backlight"
        and msg.args[0] == InOut.OUT,
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "set"
        and msg.obj.name == "scintillator-selected_pos"
        and msg.args[0] == InOut.IN
        and msg.kwargs["group"] == test_group,
    )


def test_plan_stubs_called_in_correct_order(
    sim_run_engine: RunEngineSimulator,
    robot: BartRobot,
    beamstop_phase1: Beamstop,
    scintillator: Scintillator,
    attenuator: BinaryFilterAttenuator,
    oav: OAV,
    sample_shutter: ZebraShutter,
    backlight: Backlight,
    xbpm_feedback: XBPMFeedback,
):
    messages = sim_run_engine.simulate_plan(
        take_oav_image_with_scintillator_in(
            attenuator=attenuator,
            shutter=sample_shutter,
            oav=oav,
            robot=robot,
            beamstop=beamstop_phase1,
            backlight=backlight,
            scintillator=scintillator,
            xbpm_feedback=xbpm_feedback,
        )
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "set"
        and msg.obj.name == "attenuator"
        and msg.args[0] == 1,
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "wait",
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "set"
        and msg.obj.name == "sample_shutter-control_mode"
        and msg.args[0] == ZebraShutterControl.MANUAL,
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "wait"
        and msg.kwargs["group"] == messages[0].kwargs["group"],
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "set"
        and msg.obj.name == "sample_shutter"
        and msg.args[0] == ZebraShutterState.OPEN,
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "wait"
        and msg.kwargs["group"] == messages[0].kwargs["group"],
    )


@pytest.mark.parametrize(
    "transmission",
    [1, 0.5, 0.1],
)
def test_plan_called_with_specified_transmission_then_transmission_set(
    sim_run_engine: RunEngineSimulator,
    robot: BartRobot,
    beamstop_phase1: Beamstop,
    scintillator: Scintillator,
    attenuator: BinaryFilterAttenuator,
    oav: OAV,
    sample_shutter: ZebraShutter,
    backlight: Backlight,
    xbpm_feedback: XBPMFeedback,
    transmission: float,
):
    messages = sim_run_engine.simulate_plan(
        take_oav_image_with_scintillator_in(
            transmission=transmission,
            attenuator=attenuator,
            shutter=sample_shutter,
            oav=oav,
            robot=robot,
            beamstop=beamstop_phase1,
            backlight=backlight,
            scintillator=scintillator,
            xbpm_feedback=xbpm_feedback,
        )
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "set"
        and msg.obj.name == "attenuator"
        and msg.args[0] == transmission,
    )


def test_oav_image(sim_run_engine: RunEngineSimulator, oav: OAV):
    mock_filepath = "mock_path"
    mock_filename = "mock_file"
    messages = sim_run_engine.simulate_plan(
        take_and_save_oav_image(mock_filename, mock_filepath, oav)
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "set"
        and msg.obj.name == "oav-snapshot-filename"
        and msg.args[0] == mock_filename,
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "set"
        and msg.obj.name == "oav-snapshot-directory"
        and msg.args[0] == mock_filepath,
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "wait",
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "trigger" and msg.obj.name == "oav-snapshot",
    )


@patch(
    "mx_bluesky.beamlines.i04.oav_centering_plans.oav_imaging.os.path.exists",
    MagicMock(return_value=True),
)
def test_given_file_exists_then_take_oav_image_raises(
    sim_run_engine: RunEngineSimulator, oav: OAV
):
    with pytest.raises(FileExistsError):
        sim_run_engine.simulate_plan(
            take_and_save_oav_image("mock_file", "mock_path", oav)
        )


async def test_take_and_save_oav_image_in_re(run_engine: RunEngine, oav: OAV, tmp_path):
    expected_filename = "filename"
    expected_directory = str(tmp_path)
    run_engine(take_and_save_oav_image(expected_filename, expected_directory, oav))
    assert await oav.snapshot.filename.get_value() == expected_filename
    assert await oav.snapshot.directory.get_value() == str(expected_directory)
    oav.snapshot.trigger.assert_called_once()  # type: ignore


@pytest.fixture()
async def max_pixel() -> MaxPixel:
    async with init_devices(mock=True):
        max_pixel = MaxPixel("TEST: MAX_PIXEL", "max_pixel")

    max_pixel.trigger = MagicMock(return_value=completed_status())
    return max_pixel


def test_optimise_transmission_first_gets_max_pixel_at_100_percent(
    sim_run_engine: RunEngineSimulator,
    attenuator: BinaryFilterAttenuator,
    xbpm_feedback: XBPMFeedback,
    max_pixel: MaxPixel,
):
    max_values = [100, 75]

    def return_max_values(_):
        return {"readback": {"value": max_values.pop(0)}}

    sim_run_engine.add_handler("read", return_max_values, max_pixel.max_pixel_val.name)

    messages = sim_run_engine.simulate_plan(
        optimise_transmission_with_oav(
            max_pixel=max_pixel,
            attenuator=attenuator,
            xbpm_feedback=xbpm_feedback,
        )
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "trigger" and msg.obj == xbpm_feedback,
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "set" and msg.obj == attenuator and msg.args[0] == 1,
    )

    messages = assert_message_and_return_remaining(
        messages, lambda msg: msg.command == "trigger" and msg.obj == max_pixel
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "read" and msg.obj == max_pixel.max_pixel_val,
    )


@pytest.mark.parametrize("iterations", [10, 6, 4])
def test_given_max_pixel_never_changes_then_optimise_transmission_raises_stop_iteration(
    attenuator: BinaryFilterAttenuator,
    xbpm_feedback: XBPMFeedback,
    max_pixel: MaxPixel,
    run_engine: RunEngine,
    iterations: int,
):
    set_mock_value(max_pixel.max_pixel_val, 100)

    with pytest.raises(RuntimeError) as e:
        run_engine(
            optimise_transmission_with_oav(
                max_pixel=max_pixel,
                attenuator=attenuator,
                xbpm_feedback=xbpm_feedback,
                max_iterations=iterations,
            )
        )

    # The RE hides the StopIteration behind a RuntimeError but will mention it in the message
    assert "StopIteration" in e.value.args[0]
    assert max_pixel.trigger.call_count == iterations + 1  # type: ignore


def given_max_values(max_pixel: MaxPixel, max_values: list):
    def _set_max_value():
        set_mock_value(max_pixel.max_pixel_val, max_values.pop(0))
        return completed_status()

    max_pixel.trigger.side_effect = _set_max_value  # type: ignore


@pytest.mark.parametrize(
    "lower_bound, upper_bound, expected_final_transmission",
    [[0, 100, 50], [0, 10, 5], [5, 25, 15]],
)
def test_given_max_pixel_immediately_reaches_target_then_optimise_transmission_returns_half_bounds(
    attenuator: BinaryFilterAttenuator,
    xbpm_feedback: XBPMFeedback,
    max_pixel: MaxPixel,
    run_engine: RunEngine,
    lower_bound: int,
    upper_bound: int,
    expected_final_transmission: int,
):
    given_max_values(max_pixel, [100, 75])

    final_transmission = run_engine(
        optimise_transmission_with_oav(
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            max_pixel=max_pixel,
            attenuator=attenuator,
            xbpm_feedback=xbpm_feedback,
        )
    ).plan_result  # type: ignore

    assert final_transmission == expected_final_transmission

    assert attenuator.set.call_args_list == [  # type: ignore
        call(1),
        call(expected_final_transmission / 100),
    ]


@pytest.mark.parametrize(
    "target_fraction",
    [0.75, 0.26, 0.39],
)
def test_optimise_transmission_reaches_different_target_fractions(
    attenuator: BinaryFilterAttenuator,
    xbpm_feedback: XBPMFeedback,
    max_pixel: MaxPixel,
    run_engine: RunEngine,
    target_fraction: float,
):
    given_max_values(max_pixel, [100, 100 * target_fraction])

    final_transmission = run_engine(
        optimise_transmission_with_oav(
            target_brightness_fraction=target_fraction,
            max_pixel=max_pixel,
            attenuator=attenuator,
            xbpm_feedback=xbpm_feedback,
        )
    ).plan_result  # type: ignore

    assert final_transmission == 50

    assert attenuator.set.call_args_list == [call(1), call(0.5)]  # type: ignore


def test_max_pixel_stays_too_large_then_optimise_transmission_keeps_reducing(
    attenuator: BinaryFilterAttenuator,
    xbpm_feedback: XBPMFeedback,
    max_pixel: MaxPixel,
    run_engine: RunEngine,
):
    given_max_values(max_pixel, [100, 100, 100, 100, 100, 75])

    final_transmission = run_engine(
        optimise_transmission_with_oav(
            max_pixel=max_pixel,
            attenuator=attenuator,
            xbpm_feedback=xbpm_feedback,
        )
    ).plan_result  # type: ignore

    assert final_transmission == 3.0

    assert attenuator.set.call_args_list == [  # type: ignore
        call(1),
        call(0.5),
        call(pytest.approx(0.25)),
        call(pytest.approx(0.125)),
        call(pytest.approx(0.0625)),
        call(pytest.approx(0.0312)),
    ]


def test_max_pixel_stays_too_small_then_optimise_transmission_keeps_increasing(
    attenuator: BinaryFilterAttenuator,
    xbpm_feedback: XBPMFeedback,
    max_pixel: MaxPixel,
    run_engine: RunEngine,
):
    given_max_values(max_pixel, [100, 20, 20, 20, 20, 75])

    final_transmission = run_engine(
        optimise_transmission_with_oav(
            max_pixel=max_pixel,
            attenuator=attenuator,
            xbpm_feedback=xbpm_feedback,
        )
    ).plan_result  # type: ignore

    assert final_transmission == 97.0

    assert attenuator.set.call_args_list == [  # type: ignore
        call(1),
        call(0.5),
        call(pytest.approx(0.75)),
        call(pytest.approx(0.875)),
        call(pytest.approx(0.9375)),
        call(pytest.approx(0.9688)),
    ]


@pytest.mark.parametrize(
    "tolerance, expected_final_transmission, expected_calls",
    [
        (10, 50.0, [call(1), call(0.5)]),
        (3, 75.0, [call(1), call(0.5), call(0.75)]),
    ],
)
def test_different_tolerances_change_when_we_accept(
    attenuator: BinaryFilterAttenuator,
    xbpm_feedback: XBPMFeedback,
    max_pixel: MaxPixel,
    run_engine: RunEngine,
    tolerance: int,
    expected_final_transmission: float,
    expected_calls: list,
):
    given_max_values(max_pixel, [100, 68, 75])

    final_transmission = run_engine(
        optimise_transmission_with_oav(
            tolerance=tolerance,
            max_pixel=max_pixel,
            attenuator=attenuator,
            xbpm_feedback=xbpm_feedback,
        )
    ).plan_result  # type: ignore

    assert final_transmission == expected_final_transmission
    assert attenuator.set.call_args_list == expected_calls  # type: ignore


def test_brightness_alternates_above_then_below_target_bounds_shrink_both_sides(
    attenuator: BinaryFilterAttenuator,
    xbpm_feedback: XBPMFeedback,
    max_pixel: MaxPixel,
    run_engine: RunEngine,
):
    given_max_values(max_pixel, [100, 90, 60, 85, 65, 75])

    final_transmission = run_engine(
        optimise_transmission_with_oav(
            max_pixel=max_pixel,
            attenuator=attenuator,
            xbpm_feedback=xbpm_feedback,
        )
    ).plan_result  # type: ignore

    assert final_transmission == 34.0

    # Note the 2 dp rounding on set values:
    assert attenuator.set.call_args_list == [  # type: ignore
        call(1),
        call(0.5),
        call(0.25),
        call(pytest.approx(0.375)),
        call(pytest.approx(0.3125)),
        call(pytest.approx(0.3438)),
    ]


@pytest.mark.parametrize(
    "edge_value",
    [70, 80],
)
def test_equal_to_target_plus_or_minus_tolerance_matches_target(
    attenuator: BinaryFilterAttenuator,
    xbpm_feedback: XBPMFeedback,
    max_pixel: MaxPixel,
    run_engine: RunEngine,
    edge_value: int,
):
    given_max_values(max_pixel, [100, edge_value])

    plan = optimise_transmission_with_oav(
        max_pixel=max_pixel,
        attenuator=attenuator,
        xbpm_feedback=xbpm_feedback,
    )
    plan_result = run_engine(plan).plan_result  # type: ignore

    assert plan_result == 50
    assert attenuator.set.call_args_list == [call(1), call(0.5)]  # type:ignore


def test_optimise_transmission_raises_value_error_when_upper_bound_less_than_lower_bound(
    attenuator: BinaryFilterAttenuator,
    xbpm_feedback: XBPMFeedback,
    max_pixel: MaxPixel,
    run_engine: RunEngine,
):
    with pytest.raises(ValueError) as excinfo:
        run_engine(
            optimise_transmission_with_oav(
                lower_bound=60,
                upper_bound=40,
                max_pixel=max_pixel,
                attenuator=attenuator,
                xbpm_feedback=xbpm_feedback,
            )
        )
    assert "Upper bound (40) must be higher than lower bound 60" in str(excinfo.value)

    # Ensure nothing was moved/triggered since the
    assert attenuator.set.call_count == 0  # type: ignore
    assert xbpm_feedback.trigger.call_count == 0  # type: ignore


def test_optimise_transmission_raises_value_error_when_full_beam_brightness_is_zero(
    attenuator: BinaryFilterAttenuator,
    xbpm_feedback: XBPMFeedback,
    max_pixel: MaxPixel,
    run_engine: RunEngine,
):
    given_max_values(max_pixel, [0])

    with pytest.raises(ValueError) as excinfo:
        run_engine(
            optimise_transmission_with_oav(
                max_pixel=max_pixel,
                attenuator=attenuator,
                xbpm_feedback=xbpm_feedback,
            )
        )

    assert "No beam" in str(excinfo.value)

    assert attenuator.set.call_count == 1  # type:ignore
