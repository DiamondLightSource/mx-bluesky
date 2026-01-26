from unittest.mock import AsyncMock, MagicMock, call, patch

import bluesky.plan_stubs as bps
import pytest
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
from dodal.devices.backlight import Backlight
from dodal.devices.i04.beam_centre import CentreEllipseMethod
from dodal.devices.i04.max_pixel import MaxPixel
from dodal.devices.mx_phase1.beamstop import Beamstop, BeamstopPositions
from dodal.devices.oav.oav_detector import OAV, ZoomControllerWithBeamCentres
from dodal.devices.robot import BartRobot, PinMounted
from dodal.devices.scintillator import InOut, Scintillator
from dodal.devices.xbpm_feedback import XBPMFeedback
from dodal.devices.zebra.zebra_controlled_shutter import (
    ZebraShutter,
    ZebraShutterControl,
    ZebraShutterState,
)
from ophyd_async.core import (
    AsyncStatus,
    completed_status,
    get_mock_put,
    init_devices,
    set_mock_value,
)

from mx_bluesky.beamlines.i04.oav_centering_plans.oav_imaging import (
    _prepare_beamline_for_scintillator_images,
    find_beam_centres,
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
def test_given_transmission_change_always_high_then_raises_stop_iteration(
    attenuator: BinaryFilterAttenuator,
    xbpm_feedback: XBPMFeedback,
    max_pixel: MaxPixel,
    run_engine: RunEngine,
    iterations: int,
):
    set_mock_value(max_pixel.max_pixel_val, 100)

    @AsyncStatus.wrap
    async def fake_attenuator_set(val):
        set_mock_value(attenuator.actual_transmission, val + 0.2)

    attenuator.set = MagicMock(side_effect=fake_attenuator_set)

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
async def test_given_max_pixel_immediately_reaches_target_then_optimise_transmission_returns_half_bounds(
    attenuator: BinaryFilterAttenuator,
    xbpm_feedback: XBPMFeedback,
    max_pixel: MaxPixel,
    run_engine: RunEngine,
    lower_bound: int,
    upper_bound: int,
    expected_final_transmission: int,
):
    given_max_values(max_pixel, [100, 75])

    run_engine(
        optimise_transmission_with_oav(
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            max_pixel=max_pixel,
            attenuator=attenuator,
            xbpm_feedback=xbpm_feedback,
        )
    )

    final_transmission = (await attenuator.actual_transmission.get_value()) * 100
    assert final_transmission == expected_final_transmission

    assert attenuator.set.call_args_list == [  # type: ignore
        call(1),
        call(expected_final_transmission / 100),
    ]


@pytest.mark.parametrize(
    "target_fraction",
    [0.75, 0.26, 0.39],
)
async def test_optimise_transmission_reaches_different_target_fractions(
    attenuator: BinaryFilterAttenuator,
    xbpm_feedback: XBPMFeedback,
    max_pixel: MaxPixel,
    run_engine: RunEngine,
    target_fraction: float,
):
    given_max_values(max_pixel, [100, 100 * target_fraction])

    run_engine(
        optimise_transmission_with_oav(
            target_brightness_fraction=target_fraction,
            max_pixel=max_pixel,
            attenuator=attenuator,
            xbpm_feedback=xbpm_feedback,
        )
    )

    final_transmission = (await attenuator.actual_transmission.get_value()) * 100
    assert final_transmission == 50

    assert attenuator.set.call_args_list == [call(1), call(0.5)]  # type: ignore


async def test_max_pixel_stays_too_large_then_optimise_transmission_keeps_reducing(
    attenuator: BinaryFilterAttenuator,
    xbpm_feedback: XBPMFeedback,
    max_pixel: MaxPixel,
    run_engine: RunEngine,
):
    given_max_values(max_pixel, [100, 100, 100, 100, 100, 75])

    run_engine(
        optimise_transmission_with_oav(
            max_pixel=max_pixel,
            attenuator=attenuator,
            xbpm_feedback=xbpm_feedback,
        )
    )

    final_transmission = (await attenuator.actual_transmission.get_value()) * 100
    assert final_transmission == 6.25

    assert attenuator.set.call_args_list == [  # type: ignore
        call(1),
        call(0.5),
        call(pytest.approx(0.25)),
        call(pytest.approx(0.125)),
        call(pytest.approx(0.0625)),
    ]


async def test_max_pixel_stays_too_small_then_optimise_transmission_keeps_increasing(
    attenuator: BinaryFilterAttenuator,
    xbpm_feedback: XBPMFeedback,
    max_pixel: MaxPixel,
    run_engine: RunEngine,
):
    given_max_values(max_pixel, [100, 20, 20, 20, 20, 75])

    run_engine(
        optimise_transmission_with_oav(
            max_pixel=max_pixel,
            attenuator=attenuator,
            xbpm_feedback=xbpm_feedback,
        )
    )

    final_transmission = (await attenuator.actual_transmission.get_value()) * 100
    assert final_transmission == 93.75

    assert attenuator.set.call_args_list == [  # type: ignore
        call(1),
        call(0.5),
        call(pytest.approx(0.75)),
        call(pytest.approx(0.875)),
        call(pytest.approx(0.9375)),
    ]


@pytest.mark.parametrize(
    "min_trans_change, expected_final_transmission, expected_calls",
    [
        (30, 50.0, [call(1), call(0.5)]),
        (15, 75.0, [call(1), call(0.5), call(0.75)]),
    ],
)
async def test_different_min_trans_change_change_when_we_accept(
    attenuator: BinaryFilterAttenuator,
    xbpm_feedback: XBPMFeedback,
    max_pixel: MaxPixel,
    run_engine: RunEngine,
    min_trans_change: int,
    expected_final_transmission: float,
    expected_calls: list,
):
    given_max_values(max_pixel, [100, 68, 75])

    run_engine(
        optimise_transmission_with_oav(
            min_transmission_change=min_trans_change,
            max_pixel=max_pixel,
            attenuator=attenuator,
            xbpm_feedback=xbpm_feedback,
        )
    )

    final_transmission = (await attenuator.actual_transmission.get_value()) * 100

    assert final_transmission == expected_final_transmission
    assert attenuator.set.call_args_list == expected_calls  # type: ignore


async def test_brightness_alternates_above_then_below_target_bounds_shrink_both_sides(
    attenuator: BinaryFilterAttenuator,
    xbpm_feedback: XBPMFeedback,
    max_pixel: MaxPixel,
    run_engine: RunEngine,
):
    given_max_values(max_pixel, [100, 90, 60, 85, 65, 75])

    run_engine(
        optimise_transmission_with_oav(
            max_pixel=max_pixel,
            attenuator=attenuator,
            xbpm_feedback=xbpm_feedback,
        )
    )

    final_transmission = (await attenuator.actual_transmission.get_value()) * 100
    assert final_transmission == 31.25

    # Note the 2 dp rounding on set values:
    assert attenuator.set.call_args_list == [  # type: ignore
        call(1),
        call(0.5),
        call(0.25),
        call(pytest.approx(0.375)),
        call(pytest.approx(0.3125)),
    ]


async def test_equal_to_target_matches_target(
    attenuator: BinaryFilterAttenuator,
    xbpm_feedback: XBPMFeedback,
    max_pixel: MaxPixel,
    run_engine: RunEngine,
):
    given_max_values(max_pixel, [100, 75])

    run_engine(
        optimise_transmission_with_oav(
            max_pixel=max_pixel,
            attenuator=attenuator,
            xbpm_feedback=xbpm_feedback,
            target_brightness_fraction=0.75,
        )
    )

    final_transmission = (await attenuator.actual_transmission.get_value()) * 100
    assert final_transmission == 50
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


@pytest.fixture()
async def centre_ellipse() -> CentreEllipseMethod:
    async with init_devices(mock=True):
        centre_ellipse = CentreEllipseMethod("", "centre_ellipse")

    centre_ellipse.trigger = MagicMock(return_value=completed_status())
    return centre_ellipse


def initialise_zoom_centres(
    zoom_controller: ZoomControllerWithBeamCentres, init_values: dict
):
    for i, (level, beam_centre) in enumerate(init_values.items()):
        centre_device = zoom_controller.beam_centres[i]
        set_mock_value(centre_device.level_name, level)
        set_mock_value(centre_device.x_centre, beam_centre[0])
        set_mock_value(centre_device.y_centre, beam_centre[1])


@pytest.fixture()
async def zoom_controller_with_centres() -> ZoomControllerWithBeamCentres:
    async with init_devices(mock=True):
        zoom_controller_with_centres = ZoomControllerWithBeamCentres(
            "", "zoom_controller_with_centres"
        )

    level_names = ["1.0x", "2.0x", "3.0x", "7.5x"]
    initialise_zoom_centres(
        zoom_controller_with_centres, dict.fromkeys(level_names, (0, 0))
    )

    return zoom_controller_with_centres


@pytest.fixture()
def find_beam_centre_devices(
    robot: BartRobot,
    beamstop_phase1: Beamstop,
    backlight: Backlight,
    scintillator: Scintillator,
    xbpm_feedback: XBPMFeedback,
    max_pixel: MaxPixel,
    centre_ellipse: CentreEllipseMethod,
    attenuator: BinaryFilterAttenuator,
    zoom_controller_with_centres: ZoomControllerWithBeamCentres,
    sample_shutter: ZebraShutter,
):
    return {
        "robot": robot,
        "beamstop": beamstop_phase1,
        "backlight": backlight,
        "scintillator": scintillator,
        "xbpm_feedback": xbpm_feedback,
        "max_pixel": max_pixel,
        "centre_ellipse": centre_ellipse,
        "attenuator": attenuator,
        "zoom_controller": zoom_controller_with_centres,
        "shutter": sample_shutter,
    }


def test_given_levels_to_centre_that_dont_exist_when_find_beam_centres_exception_raised(
    find_beam_centre_devices: dict,
    run_engine: RunEngine,
):
    with pytest.raises(ValueError):
        run_engine(
            find_beam_centres(
                zoom_levels_to_centre=("bad_zoom"), **find_beam_centre_devices
            )
        )


def test_given_levels_to_optimise_that_dont_exist_when_find_beam_centres_exception_raised(
    find_beam_centre_devices: dict,
    run_engine: RunEngine,
):
    with pytest.raises(ValueError):
        run_engine(
            find_beam_centres(
                zoom_levels_to_optimise_transmission=("bad_zoom"),
                **find_beam_centre_devices,
            )
        )


@patch(
    "mx_bluesky.beamlines.i04.oav_centering_plans.oav_imaging._prepare_beamline_for_scintillator_images"
)
@patch(
    "mx_bluesky.beamlines.i04.oav_centering_plans.oav_imaging.optimise_transmission_with_oav",
    new=MagicMock(),
)
def test_find_beam_centres_starts_by_prepping_scintillator(
    mock_prepare_scintillator: AsyncMock,
    find_beam_centre_devices: dict,
    run_engine: RunEngine,
):
    run_engine(find_beam_centres(**find_beam_centre_devices))
    mock_prepare_scintillator.assert_called_once()
    assert find_beam_centre_devices["centre_ellipse"].trigger.call_count == 4  # type: ignore


def mock_centre_ellipse_with_given_centres(
    centre_ellipse: CentreEllipseMethod, given_centres: list[tuple[int, int]]
):
    def centre_ellipse_trigger_side_effect(*args):
        next_centre = given_centres.pop(0)
        set_mock_value(centre_ellipse.center_x_val, next_centre[0])
        set_mock_value(centre_ellipse.center_y_val, next_centre[1])
        return completed_status()

    centre_ellipse.trigger.side_effect = centre_ellipse_trigger_side_effect  # type:ignore


@patch(
    "mx_bluesky.beamlines.i04.oav_centering_plans.oav_imaging._prepare_beamline_for_scintillator_images",
    new=MagicMock(),
)
@patch(
    "mx_bluesky.beamlines.i04.oav_centering_plans.oav_imaging.optimise_transmission_with_oav",
    new=MagicMock(),
)
async def test_find_beam_centres_iterates_and_sets_centres(
    find_beam_centre_devices: dict,
    run_engine: RunEngine,
):
    level_names = ["1.0x", "2.0x", "3.0x", "7.5x"]
    new_centres = [(100, 100), (200, 200), (300, 300), (400, 400)]
    expected_centres = new_centres.copy()

    centre_ellipse = find_beam_centre_devices["centre_ellipse"]
    zoom_controller_with_centres: ZoomControllerWithBeamCentres = (
        find_beam_centre_devices["zoom_controller"]
    )

    mock_centre_ellipse_with_given_centres(centre_ellipse, new_centres)

    run_engine(find_beam_centres(**find_beam_centre_devices))

    assert get_mock_put(zoom_controller_with_centres.level).call_count == 4
    assert get_mock_put(zoom_controller_with_centres.level).call_args_list == [
        call(level, wait=True) for level in level_names
    ]

    for i, centre in zoom_controller_with_centres.beam_centres.items():
        level_name = await centre.level_name.get_value()
        if level_name:
            assert level_name == level_names[i]
            assert (await centre.x_centre.get_value()) == expected_centres[i][0]
            assert (await centre.y_centre.get_value()) == expected_centres[i][1]


@patch(
    "mx_bluesky.beamlines.i04.oav_centering_plans.oav_imaging._prepare_beamline_for_scintillator_images",
    new=MagicMock(),
)
@patch(
    "mx_bluesky.beamlines.i04.oav_centering_plans.oav_imaging.optimise_transmission_with_oav",
    new=MagicMock(),
)
async def test_if_only_some_levels_given_then_find_beam_centres_iterates_and_sets_those_centres(
    find_beam_centre_devices: dict,
    run_engine: RunEngine,
):
    new_centres = [(100, 100), (200, 200), (300, 300), (400, 400)]

    centre_ellipse = find_beam_centre_devices["centre_ellipse"]
    zoom_controller_with_centres: ZoomControllerWithBeamCentres = (
        find_beam_centre_devices["zoom_controller"]
    )

    mock_centre_ellipse_with_given_centres(centre_ellipse, new_centres)

    run_engine(
        find_beam_centres(
            zoom_levels_to_centre=["1.0x", "7.5x"], **find_beam_centre_devices
        )
    )

    assert get_mock_put(zoom_controller_with_centres.level).call_count == 2
    assert get_mock_put(zoom_controller_with_centres.level).call_args_list == [
        call(level, wait=True) for level in ["1.0x", "7.5x"]
    ]

    centres = list(zoom_controller_with_centres.beam_centres.values())

    assert (await centres[0].level_name.get_value()) == "1.0x"
    assert (await centres[0].x_centre.get_value()) == 100
    assert (await centres[0].y_centre.get_value()) == 100

    for centre in [centres[1], centres[2]]:
        assert (await centre.x_centre.get_value()) == 0
        assert (await centre.y_centre.get_value()) == 0

    assert (await centres[3].level_name.get_value()) == "7.5x"
    assert (await centres[3].x_centre.get_value()) == 200
    assert (await centres[3].y_centre.get_value()) == 200


@patch(
    "mx_bluesky.beamlines.i04.oav_centering_plans.oav_imaging._prepare_beamline_for_scintillator_images",
    new=MagicMock(),
)
@patch(
    "mx_bluesky.beamlines.i04.oav_centering_plans.oav_imaging.optimise_transmission_with_oav"
)
async def test_find_beam_centres_optimises_on_default_levels_only(
    mock_optimise: MagicMock,
    find_beam_centre_devices: dict,
    run_engine: RunEngine,
):
    levels_where_optimised = []

    zoom_controller_with_centres: ZoomControllerWithBeamCentres = (
        find_beam_centre_devices["zoom_controller"]
    )

    def append_current_zoom(*args, **kwargs):
        current_zoom = yield from bps.rd(zoom_controller_with_centres.level)
        levels_where_optimised.append(current_zoom)
        yield from bps.null()

    mock_optimise.side_effect = append_current_zoom

    run_engine(find_beam_centres(**find_beam_centre_devices))

    assert mock_optimise.call_count == 2
    assert levels_where_optimised == ["1.0x", "7.5x"]


@patch(
    "mx_bluesky.beamlines.i04.oav_centering_plans.oav_imaging._prepare_beamline_for_scintillator_images",
    new=MagicMock(),
)
@patch(
    "mx_bluesky.beamlines.i04.oav_centering_plans.oav_imaging.optimise_transmission_with_oav"
)
async def test_find_beam_centres_respects_custom_optimise_list(
    mock_optimise: MagicMock,
    find_beam_centre_devices: dict,
    run_engine: RunEngine,
):
    levels_where_optimised = []

    zoom_controller_with_centres: ZoomControllerWithBeamCentres = (
        find_beam_centre_devices["zoom_controller"]
    )

    def append_current_zoom(*args, **kwargs):
        current_zoom = yield from bps.rd(zoom_controller_with_centres.level)
        levels_where_optimised.append(current_zoom)
        yield from bps.null()

    mock_optimise.side_effect = append_current_zoom

    run_engine(
        find_beam_centres(
            zoom_levels_to_optimise_transmission=["2.0x", "3.0x"],
            **find_beam_centre_devices,
        )
    )

    assert mock_optimise.call_count == 2
    assert levels_where_optimised == ["2.0x", "3.0x"]
