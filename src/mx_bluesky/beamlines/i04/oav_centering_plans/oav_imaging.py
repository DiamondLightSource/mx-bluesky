import os
import time

import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.common import inject
from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
from dodal.devices.backlight import Backlight
from dodal.devices.beamlines.i04.beam_centre import CentreEllipseMethod
from dodal.devices.beamlines.i04.max_pixel import MaxPixel
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

OAV_PREPARE_BEAMLINE_FOR_SCINT_WAIT = "Wait for scint to move in"


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

    LOGGER.info("Preparing beamline to take scintillator images...")
    yield from _prepare_beamline_for_scintillator_images(
        robot,
        beamstop,
        backlight,
        scintillator,
        xbpm_feedback,
        shutter,
        OAV_PREPARE_BEAMLINE_FOR_SCINT_WAIT,
    )
    yield from bps.abs_set(
        attenuator, transmission, group=OAV_PREPARE_BEAMLINE_FOR_SCINT_WAIT
    )

    if image_name is None:
        image_name = f"{time.time_ns()}ATT{transmission * 100}"
    LOGGER.info(f"Using image name {image_name}")
    LOGGER.info("Waiting for prepare beamline plan to complete...")
    yield from bps.wait(OAV_PREPARE_BEAMLINE_FOR_SCINT_WAIT)

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
    the beam is on (feedback check). Finally, the scintillator is moved in and the
    shutter opened.
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
    # Not waiting for control mode to be set before opening shutter can result in timeout error
    yield from bps.abs_set(shutter.control_mode, ZebraShutterControl.MANUAL, wait=True)
    yield from bps.abs_set(shutter, ZebraShutterState.OPEN, group=group)


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
    # Potential controls issue on XBPM device means it can mark
    # itself as stable before it really is
    yield from bps.trigger(xbpm_feedback, wait=True)
    yield from bps.mv(attenuator, transmission)
    yield from bps.trigger(max_pixel, wait=True)
    return (yield from bps.rd(max_pixel.max_pixel_val))


def optimise_transmission_with_oav(
    upper_bound: float = 100,
    lower_bound: float = 0,
    target_brightness_fraction: float = 0.75,
    min_transmission_change: float = 5,
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
        min_transmission_change: If the next search point would require a transmission
                    change less than this then we stop.
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

        current_transmission = yield from bps.rd(attenuator.actual_transmission)
        transmission_change_percent = abs(mid - current_transmission * 100)
        if transmission_change_percent < min_transmission_change:
            LOGGER.info(
                f"Next transmission change would be small ({transmission_change_percent}%) so stopping at {current_transmission}"
            )
            return

        brightest_pixel = yield from _max_pixel_at_transmission(
            max_pixel, attenuator, xbpm_feedback, mid / 100
        )

        LOGGER.info(f"Upper bound is: {upper_bound}, Lower bound is: {lower_bound}")
        LOGGER.info(
            f"Testing transmission {mid}, brightest pixel found {brightest_pixel}"
        )

        if target_pixel_brightness == brightest_pixel:
            mid = round(mid, 0)
            LOGGER.info(f"\nOptimal transmission found: {mid}")
            return

        # condition for too low so want to try higher
        elif brightest_pixel < target_pixel_brightness:
            LOGGER.info("Result: Too low \n")
            lower_bound = mid

        # condition for too high so want to try lower
        elif brightest_pixel > target_pixel_brightness:
            LOGGER.info("Result: Too high \n")
            upper_bound = mid
        iterations += 1
    raise StopIteration("Max iterations reached")


def _get_all_zoom_levels(
    zoom_controller: ZoomControllerWithBeamCentres,
) -> MsgGenerator[tuple[str]]:
    zoom_levels = []
    level_signals = [
        centring_device.level_name
        for centring_device in zoom_controller.beam_centres.values()
    ]
    for signal in level_signals:
        level_name = yield from bps.rd(signal)
        if level_name:
            zoom_levels.append(level_name)
    return tuple(zoom_levels)


def find_beam_centres(
    zoom_levels_to_centre: tuple[str, ...] | None = None,
    zoom_levels_to_optimise_transmission: tuple[str, ...] = ("1.0x", "7.5x"),
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
    Finds beam centres at the zoom levels given by zoom_levels_to_centre, first
    optimising transmission if the zoom level is in zoom_levels_to_optimise_transmission.

    Note that the previous beam centre values are used to draw an ROI box around the
    OAV image when finding updated beam centre. If the previous values are very wrong,
    this plan may fail or give inaccurate results.

    zoom_levels_to_centre: The levels to do centring at, by default runs at all known
                           zoom levels.
    zoom_levels_to_optimise_transmission: The levels to optimise transmission at,
                           defaults to 1x and 7.5x
    """

    all_zooms = yield from _get_all_zoom_levels(zoom_controller)
    if zoom_levels_to_centre is None:
        zoom_levels_to_centre = all_zooms

    for zoom in [*zoom_levels_to_optimise_transmission, *zoom_levels_to_centre]:
        if zoom not in all_zooms:
            raise ValueError(f"Unknown zoom ({zoom}). Known zooms are {all_zooms}")

    LOGGER.info("Preparing beamline for images...")
    yield from _prepare_beamline_for_scintillator_images(
        robot,
        beamstop,
        backlight,
        scintillator,
        xbpm_feedback,
        shutter,
        OAV_PREPARE_BEAMLINE_FOR_SCINT_WAIT,
    )
    LOGGER.info("Waiting for prepare beamline plan to complete...")
    yield from bps.wait(OAV_PREPARE_BEAMLINE_FOR_SCINT_WAIT)

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
            LOGGER.info(
                f"Writing centre values ({centre_x}, {centre_y}) to OAV PVs at zoom level {zoom_name}"
            )
            yield from bps.mv(
                centring_device.x_centre, centre_x, centring_device.y_centre, centre_y
            )

    LOGGER.info("Find beam centre plan completed!")


def find_and_set_beam_centre_at_current_zoom_and_transmission(
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
):
    """Finds the beam centre at the current zoom level."""
    current_zoom_level = yield from bps.rd(zoom_controller.level)
    yield from find_beam_centres(
        zoom_levels_to_centre=(current_zoom_level,),
        zoom_levels_to_optimise_transmission=(),
        robot=robot,
        beamstop=beamstop,
        backlight=backlight,
        scintillator=scintillator,
        xbpm_feedback=xbpm_feedback,
        max_pixel=max_pixel,
        centre_ellipse=centre_ellipse,
        attenuator=attenuator,
        zoom_controller=zoom_controller,
        shutter=shutter,
    )
