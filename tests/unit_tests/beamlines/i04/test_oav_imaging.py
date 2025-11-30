from collections.abc import AsyncGenerator
from unittest.mock import MagicMock, patch

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
from ophyd_async.core import init_devices
from ophyd_async.testing import set_mock_value

from mx_bluesky.beamlines.i04.oav_centering_plans.oav_imaging import (
    _prepare_beamline_for_scintillator_images,
    take_and_save_oav_image,
    take_oav_image_with_scintillator_in,
)
from mx_bluesky.common.utils.exceptions import BeamlineStateError
from mx_bluesky.common.utils.log import LOGGER


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
):
    test_group = "my_group"
    messages = sim_run_engine.simulate_plan(
        _prepare_beamline_for_scintillator_images(
            robot, beamstop_phase1, backlight, scintillator, xbpm_feedback, test_group
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


# add test for transmission optimization
# test that everything is called in the correct order.
# mock out the different transmissions and max vals and make sure you reach what's expected.


@pytest.fixture()
async def max_pixel() -> AsyncGenerator[MaxPixel]:
    async with init_devices(mock=True):
        max_pixel = MaxPixel("TEST: MAX_PIXEL")
    yield max_pixel


@patch("mx_bluesky.beamlines.i04.oav_centering_plans.oav_imaging.brightest_pixel_sat")
def test_binary_search(
    mock_brightest_pixel: MagicMock,
    max_pixel: MaxPixel,
    attenuator: BinaryFilterAttenuator,
    upper_bound=100,
    lower_bound=0,
):
    mock_brightest_pixel.return_value()


# # mock function transmission optimisation
# @pytest.fixture
# def get_max_pixel_value_from_transmission(transmission) -> float:
#     return transmission + 10

# @pytest.fixture
# def get_max_pixel_value_from_transmission(max_pixel: MaxPixel) :
#     max_pixel.max_pixel_val.read = AsyncMock([100, 3, 2], [200, 3, 90], [255/2, 90, 80])

# async def test_optimise_oav_transmission_binary_search(
#     get_max_pixel_value_from_transmission, run_engine: RunEngine, max_pixel: MaxPixel, attenuator: BinaryFilterAttenuator
# ):
#     pass
# ----------------------------

# # if target is set to 50, then we are expecting optimal transmission to be 40
# def mid_logic(upper, lower):

# @patch(
#     "mx_bluesky.beamlines.i04.oav_centering_plans.oav_imaging.brightest_pixel_sat", 255
# )
# @patch(
#     "mx_bluesky.beamlines.i04.oav_centering_plans.oav_imaging.brightest_pixel",
#     get_max_pixel_value_from_transmission(),
# )
# def test_optimise_oav_transmission_binary_search(
#     get_max_pixel_value_from_transmission, run_engine: RunEngine, max_pixel: MaxPixel, attenuator: BinaryFilterAttenuator
# ):
#     upper_bound = 100
#     lower_bound = 0
#     frac_of_max = 0.5
#     run_engine(optimise_oav_transmission_binary_search(upper_bound, lower_bound, max_pixel = max_pixel, attenuator=attenuator))
#     max_pixel_values = [50, 75, 87.5]

#     async def get_max_pixel_val():
#         upper = 50
#         for i in range(5):
#             yield

#     max_pixel.max_pixel_val.read = AsyncMock(side_effect=get_max_pixel_val)
#     set_mock_value()


#     with patch("mx_bluesky.beamlines.i04.oav_centering_plans.oav_imaging.")


def tranmission_to_max_pixel(transmission):
    max_pixel = transmission + 30
    return max_pixel
    # if target is 100 then we expect the optimal transmission to be 100 - 30 = 70


def optimise_oav_transmission_binary_search(
    upper_bound: float,  # in percent
    lower_bound: float,  # in percent
    frac_of_max: float = 0.5,
    tolerance: int = 1,
    max_iterations: int = 5,
):
    target_pixel_l = 255 * frac_of_max

    while max_iterations > tolerance:
        mid = round((upper_bound + lower_bound) / 2, 2)  # limit to 2 dp
        max_iterations -= 1

        brightest_pixel = tranmission_to_max_pixel(mid)
        # brightest_pixel = get_max_pixel_value_from_transmission(transmission=mid)
        LOGGER.info(f"Upper bound is: {upper_bound}, Lower bound is: {lower_bound}")
        LOGGER.info(
            f"Testing transmission {mid}, brightest pixel found {brightest_pixel}"
        )

        if target_pixel_l - tolerance < brightest_pixel < target_pixel_l + tolerance:
            mid = round(mid, 0)
            LOGGER.info(f"\nOptimal transmission found - {mid}")
            return mid

        # condition for too low so want to try higher
        elif brightest_pixel < target_pixel_l - tolerance:
            LOGGER.info("Result: Too low \n")
            lower_bound = mid

        # condition for too high so want to try lower
        elif brightest_pixel > target_pixel_l + tolerance:
            LOGGER.info("Result: Too high \n")
            upper_bound = mid
    return "Max iterations reached"


def test_binary_search_logic():
    search = optimise_oav_transmission_binary_search(100, 0)
    assert search == 70
