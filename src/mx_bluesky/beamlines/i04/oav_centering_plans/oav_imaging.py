import os
import time

import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.common import inject
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
from ophyd_async.core import InOut as core_INOUT

from mx_bluesky.common.utils.exceptions import BeamlineStateError
from mx_bluesky.common.utils.log import LOGGER

initial_wait_group = "Wait for scint to move in"


def take_oav_image_with_scintillator_in(
    image_name: str | None = None,
    image_path: str = "dls_sw/i04/software/bluesky/scratch",
    transmission: float = 1,
    attenuator: BinaryFilterAttenuator = inject("attenuator"),
    shutter: ZebraShutter = inject("sample_shutter"),
    oav: OAV = inject("oav"),
    robot: BartRobot = inject("robot"),
    beamstop: Beamstop = inject("beamstop"),
    backlight: Backlight = inject("backlight"),
    scintillator: Scintillator = inject("scintillator"),
    xbpm_feedback: XBPMFeedback = inject("xbpm_feedback"),
) -> MsgGenerator:
    """
    Takes an OAV image at specified transmission after necessary checks and preparation steps.

    Args:
        image_name: Name of the OAV image to be saved
        image_path: Path where the image should be saved
        transmission: Transmission of the beam, takes a value from 0 to 1 where
                    1 lets all the beam through and 0 lets none of the beam through.
        devices: These are the specific ophyd-devices used for the plan, the
                    defaults are always correct.
    """

    yield from _prepare_beamline_for_scintillator_images(
        robot, beamstop, backlight, scintillator, xbpm_feedback, initial_wait_group
    )

    yield from bps.abs_set(attenuator, transmission, group=initial_wait_group)

    if image_name is None:
        image_name = f"{time.time_ns()}ATT{transmission * 100}"

    yield from bps.wait(initial_wait_group)

    yield from bps.abs_set(shutter.control_mode, ZebraShutterControl.MANUAL, wait=True)
    yield from bps.abs_set(shutter, ZebraShutterState.OPEN, wait=True)

    take_and_save_oav_image(file_path=image_path, file_name=image_name, oav=oav)


def _prepare_beamline_for_scintillator_images(
    robot: BartRobot,
    beamstop: Beamstop,
    backlight: Backlight,
    scintillator: Scintillator,
    xbpm_feedback: XBPMFeedback,
    group: str,
) -> MsgGenerator:
    """
    Prepares the beamline for oav image by making sure the pin is NOT mounted and
    the beam is on (feedback check). Finally, the scintillator is moved in.

     Args:
        devices: These are the specific ophyd-devices used for the plan, the
                    defaults are always correct.
    """
    pin_mounted = yield from bps.rd(robot.gonio_pin_sensor)
    if pin_mounted == PinMounted.PIN_MOUNTED:
        raise BeamlineStateError("Pin should not be mounted!")

    yield from bps.trigger(xbpm_feedback, group=group)

    yield from bps.abs_set(
        beamstop.selected_pos, BeamstopPositions.DATA_COLLECTION, group=group
    )

    yield from bps.abs_set(backlight, core_INOUT.OUT, group=group)

    yield from bps.abs_set(scintillator.selected_pos, InOut.IN, group=group)


def take_and_save_oav_image(
    file_name: str,
    file_path: str,
    oav: OAV,
) -> MsgGenerator:
    """
    Plan which takes and saves an OAV image to the specified path.
     Args:
        file_name: Filename specifying the name of the image,
        file_path: Path as a string specifying where the image should be saved,
        oav: The OAV to take the image with
    """
    group = "oav image path setting"
    full_file_path = file_path + "/" + file_name
    if not os.path.exists(full_file_path):
        yield from bps.abs_set(oav.snapshot.filename, file_name, group=group)
        yield from bps.abs_set(oav.snapshot.directory, file_path, group=group)
        yield from bps.wait(group, timeout=60)
        yield from bps.trigger(oav.snapshot, wait=True)
    else:
        raise FileExistsError("OAV image file path already exists")


def _get_max_pixel_from_100_transmission(
    max_pixel: MaxPixel = inject("max_pixel"),
    attenuator: BinaryFilterAttenuator = inject("attenuator"),
):
    yield from bps.mv(attenuator, 100)  # 100 % transmission
    yield from bps.trigger(max_pixel, wait=True)
    target_brightest_pixel = yield from bps.rd(max_pixel.max_pixel_val)
    return target_brightest_pixel


def optimise_oav_transmission_binary_search(
    upper_bound: float,  # in percent
    lower_bound: float,  # in percent
    frac_of_max: float = 0.5,
    tolerance: int = 1,
    max_iterations: int = 5,
    max_pixel: MaxPixel = inject("max_pixel"),
    attenuator: BinaryFilterAttenuator = inject("attenuator"),
):
    """
    Plan to find the optimal oav transmission. First the brightest pixel at 100%
    transmission is taken. A fraction of this (frac_of_max) is taken as the target -
    as in the optimal transmission will have it's max pixel as the set target.
    A binary search is used to reach the target.
    Args:
        upper_bound: Maximum transmission which will be searched.
        lower_bound: Minimum transmission which will be searched.
        frac_of_max: Fraction of the brightest pixel at 100% transmission which should be
                     used as the target max pixel brightness.
        tolerance: Amount the search can be off by and still find a match.
        max_iterations: Maximum amount of iterations.
    """
    brightest_pixel_sat = yield from _get_max_pixel_from_100_transmission()
    target_pixel_l = brightest_pixel_sat * frac_of_max
    LOGGER.info(f"~~Target luminosity: {target_pixel_l}~~\n")

    while max_iterations > tolerance:
        mid = round((upper_bound + lower_bound) / 2, 2)  # limit to 2 dp
        max_iterations -= 1

        yield from bps.mv(attenuator, mid / 100)
        yield from bps.trigger(max_pixel, wait=True)
        brightest_pixel = yield from bps.rd(max_pixel.max_pixel_val)

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
    raise StopIteration("Max iterations reached")
