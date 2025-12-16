import os
import time

import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.common import inject
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

    LOGGER.info("prearing beamline")
    yield from _prepare_beamline_for_scintillator_images(
        robot,
        beamstop,
        backlight,
        scintillator,
        xbpm_feedback,
        shutter,
        initial_wait_group,
    )
    LOGGER.info("setting transmission")
    yield from bps.abs_set(attenuator, transmission, group=initial_wait_group)

    if image_name is None:
        image_name = f"{time.time_ns()}ATT{transmission * 100}"
    LOGGER.info(f"using image name {image_name}")
    LOGGER.info("Waiting for initial_wait_group...")
    yield from bps.wait(initial_wait_group)

    LOGGER.info("Opening shutter...")

    yield from bps.abs_set(shutter.control_mode, ZebraShutterControl.MANUAL, wait=True)
    yield from bps.abs_set(shutter, ZebraShutterState.OPEN, wait=True)

    LOGGER.info("Taking image...")

    yield from take_and_save_oav_image(
        file_path=image_path, file_name=image_name, oav=oav
    )


def _prepare_beamline_for_scintillator_images(
    robot: BartRobot,
    beamstop: Beamstop,
    backlight: Backlight,
    scintillator: Scintillator,
    xbpm_feedback: XBPMFeedback,
    shutter: ZebraShutter,
    group: str,
) -> MsgGenerator:
    """
    Prepares the beamline for oav image by making sure the pin is not mounted and
    the beam is on (feedback check). Finally, the scintillator is moved in.
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

    yield from bps.abs_set(shutter.control_mode, ZebraShutterControl.MANUAL, wait=True)
    yield from bps.abs_set(shutter, ZebraShutterState.OPEN, wait=True)


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


def _max_pixel_at_transmission(
    max_pixel: MaxPixel,
    attenuator: BinaryFilterAttenuator,
    xbpm_feedback: XBPMFeedback,
    transmission: float,
):
    yield from bps.trigger(xbpm_feedback, wait=True)
    yield from bps.mv(attenuator, transmission)
    yield from bps.trigger(max_pixel, wait=True)
    return (yield from bps.rd(max_pixel.max_pixel_val))


def optimise_transmission_with_oav(
    upper_bound: float = 100,
    lower_bound: float = 0,
    target_brightness_fraction: float = 0.75,
    tolerance: int = 5,
    max_iterations: int = 10,
    max_pixel: MaxPixel = inject("max_pixel"),
    attenuator: BinaryFilterAttenuator = inject("attenuator"),
    xbpm_feedback: XBPMFeedback = inject("xbpm_feedback"),
) -> MsgGenerator:
    """
    Plan to find the optimal oav transmission. First the brightest pixel at 100%
    transmission is taken. A fraction of this (target_brightness_fraction) is taken
    as the target - as in the optimal transmission will have it's max pixel as the set
    target. A binary search is used to reach this.
    Args:
        upper_bound: Maximum transmission which will be searched. In percent.
        lower_bound: Minimum transmission which will be searched. In percent.
        target_brightness_fraction: Fraction of the brightest pixel at 100%
                    transmission which should be used as the target max pixel brightness.
        tolerance: Amount the brightness can be off by and still find a match.
        max_iterations: Maximum amount of iterations.
    """

    if upper_bound < lower_bound:
        raise ValueError(
            f"Upper bound ({upper_bound}) must be higher than lower bound {lower_bound}"
        )

    brightest_pixel_at_full_beam = yield from _max_pixel_at_transmission(
        max_pixel, attenuator, xbpm_feedback, 1
    )

    if brightest_pixel_at_full_beam == 0:
        raise ValueError("No beam found at full transmission")

    target_pixel_brightness = brightest_pixel_at_full_beam * target_brightness_fraction
    LOGGER.info(
        f"Optimising until max pixel in image has a value of {target_pixel_brightness}"
    )

    iterations = 0

    while iterations < max_iterations:
        mid = round((upper_bound + lower_bound) / 2, 2)  # limit to 2 dp
        LOGGER.info(f"On iteration {iterations}")

        brightest_pixel = yield from _max_pixel_at_transmission(
            max_pixel, attenuator, xbpm_feedback, mid / 100
        )

        LOGGER.info(f"Upper bound is: {upper_bound}, Lower bound is: {lower_bound}")
        LOGGER.info(
            f"Testing transmission {mid}, brightest pixel found {brightest_pixel}"
        )

        if (
            target_pixel_brightness - tolerance
            <= brightest_pixel
            <= target_pixel_brightness + tolerance
        ):
            mid = round(mid, 0)
            LOGGER.info(f"\nOptimal transmission found: {mid}")
            return mid

        # condition for too low so want to try higher
        elif brightest_pixel < target_pixel_brightness - tolerance:
            LOGGER.info("Result: Too low \n")
            lower_bound = mid

        # condition for too high so want to try lower
        elif brightest_pixel > target_pixel_brightness + tolerance:
            LOGGER.info("Result: Too high \n")
            upper_bound = mid
        iterations += 1
    raise StopIteration("Max iterations reached")


def _get_all_zoom_levels(
    zoom_controller: ZoomControllerWithBeamCentres,
) -> MsgGenerator[list[str]]:
    zoom_levels = []
    level_signals = [
        centring_device.level_name
        for centring_device in zoom_controller.beam_centres.values()
    ]
    for signal in level_signals:
        level_name = yield from bps.rd(signal)
        if level_name:
            zoom_levels.append(level_name)
    return zoom_levels


def find_beam_centres(
    zoom_levels_to_centre: list[str] | None = None,
    zoom_levels_to_optimise_transmission: list[str] | None = None,
    robot: BartRobot = inject("robot"),
    beamstop: Beamstop = inject("beamstop"),
    backlight: Backlight = inject("backlight"),
    scintillator: Scintillator = inject("scintillator"),
    xbpm_feedback: XBPMFeedback = inject("xbpm_feedback"),
    max_pixel: MaxPixel = inject("max_pixel"),
    centre_ellipse: CentreEllipseMethod = inject("beam_centre"),
    attenuator: BinaryFilterAttenuator = inject("attenuator"),
    zoom_controller: ZoomControllerWithBeamCentres = inject("zoom_controller"),
    shutter: ZebraShutter = inject("sample_shutter"),
) -> MsgGenerator:
    """
    zoom_levels: The levels to do centring at, by default runs at all known zoom levels.
    """
    if zoom_levels_to_optimise_transmission is None:
        zoom_levels_to_optimise_transmission = ["1.0x", "7.5x"]

    if zoom_levels_to_centre is None:
        zoom_levels_to_centre = yield from _get_all_zoom_levels(zoom_controller)

    LOGGER.info("Preparing beamline for images...")
    yield from _prepare_beamline_for_scintillator_images(
        robot,
        beamstop,
        backlight,
        scintillator,
        xbpm_feedback,
        shutter,
        initial_wait_group,
    )

    for centring_device in zoom_controller.beam_centres.values():
        zoom_name = yield from bps.rd(centring_device.level_name)
        if zoom_name in zoom_levels_to_centre:
            LOGGER.info(f"Moving to zoom level {zoom_name}")
            yield from bps.abs_set(zoom_controller, zoom_name, wait=True)
            if zoom_name in zoom_levels_to_optimise_transmission:
                LOGGER.info(f"Optimising transmission at zoom level {zoom_name}")
                yield from optimise_transmission_with_oav(
                    100,
                    0,
                    max_pixel=max_pixel,
                    attenuator=attenuator,
                    xbpm_feedback=xbpm_feedback,
                )

            yield from bps.trigger(centre_ellipse, wait=True)
            centre_x = yield from bps.rd(centre_ellipse.center_x_val)
            centre_y = yield from bps.rd(centre_ellipse.center_y_val)
            centre_x = round(centre_x)
            centre_y = round(centre_y)
            LOGGER.info(f"Writing centre values ({centre_x}, {centre_y}) to OAV PVs")
            yield from bps.mv(
                centring_device.x_centre, centre_x, centring_device.y_centre, centre_y
            )

    LOGGER.info("Done!")
