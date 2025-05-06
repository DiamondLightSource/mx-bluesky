from collections.abc import Generator

import bluesky.plan_stubs as bps
import pydantic
from blueapi.core import BlueskyContext
from bluesky.utils import Msg
from dodal.devices.backlight import Backlight
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.oav.oav_parameters import OAV_CONFIG_JSON, OAVParameters
from dodal.devices.oav.pin_image_recognition import PinTipDetection, Tip
from dodal.devices.oav.utils import (
    PinNotFoundException,
    Pixel,
    get_move_required_so_that_beam_is_at_pixel,
    wait_for_tip_to_be_found,
)
from dodal.devices.smargon import Smargon

from mx_bluesky.common.device_setup_plans.setup_oav import pre_centring_setup_oav
from mx_bluesky.common.utils.context import device_composite_from_context
from mx_bluesky.common.utils.exceptions import SampleException, catch_exception_and_warn
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.hyperion.device_setup_plans.smargon import (
    move_smargon_warn_on_out_of_range,
)
from mx_bluesky.hyperion.parameters.constants import CONST

DEFAULT_STEP_SIZE = 0.5


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class PinTipCentringComposite:
    """All devices which are directly or indirectly required by this plan"""

    backlight: Backlight
    oav: OAV
    smargon: Smargon
    pin_tip_detection: PinTipDetection


def create_devices(context: BlueskyContext) -> PinTipCentringComposite:
    return device_composite_from_context(context, PinTipCentringComposite)


def trigger_and_return_pin_tip(
    pin_tip: PinTipDetection,
) -> Generator[Msg, None, Tip]:
    yield from bps.trigger(pin_tip, wait=True)
    tip_x_y_px = yield from bps.rd(pin_tip.triggered_tip)
    LOGGER.info(f"Pin tip found at {tip_x_y_px}")
    return tip_x_y_px


def move_pin_into_view(
    pin_tip_device: PinTipDetection,
    smargon: Smargon,
    step_magnitude_mm: float = DEFAULT_STEP_SIZE,
    max_steps: int = 2,
) -> Generator[Msg, None, Pixel]:
    """Attempt to move the pin into view and return the tip location in pixels if found.
    The gonio x is moved in a number of discrete steps to find the pin. If the move
    would take it past its limit, it moves to the limit instead.

    Args:
        pin_tip_device (PinTipDetection): The device being used to detect the pin
        smargon (Smargon): The gonio to move the tip
        step_magnitude_mm (float, optional): Distance to move the gonio (in mm) for each
                                    step of the search. Defaults to 0.5.
        max_steps (int, optional): The number of steps to search with. Defaults to 2.

    Raises:
        SampleException: Error if the pin tip is never found

    Returns:
        Tuple[int, int]: The location of the pin tip in pixels
    """

    def pin_tip_valid(pin_xy: Tip):
        return not all(pin_xy == pin_tip_device.INVALID_POSITION) and pin_xy[0] != 0

    for _ in range(max_steps):
        tip_xy_px = yield from trigger_and_return_pin_tip(pin_tip_device)

        if pin_tip_valid(tip_xy_px):
            return (int(tip_xy_px[0]), int(tip_xy_px[1]))

        # Pin is off in the -ve direction if the returned tip x pixel value is 0
        direction_multiple = -1 if tip_xy_px[0] == 0 else 1
        step_vector_mm = step_magnitude_mm * direction_multiple

        smargon_x = yield from bps.rd(smargon.x.user_readback)
        ideal_move_to_find_pin = float(smargon_x) + step_vector_mm
        high_limit = yield from bps.rd(smargon.x.high_limit_travel)
        low_limit = yield from bps.rd(smargon.x.low_limit_travel)
        move_within_limits = max(min(ideal_move_to_find_pin, high_limit), low_limit)
        if move_within_limits != ideal_move_to_find_pin:
            LOGGER.warning(
                f"Pin tip is off screen, and moving {step_vector_mm}mm would cross limits, "
                f"moving to {move_within_limits} instead"
            )
        yield from bps.mv(smargon.x, move_within_limits)

        # Some time for the view to settle after the move
        yield from bps.sleep(CONST.HARDWARE.OAV_REFRESH_DELAY)

    tip_xy_px = yield from trigger_and_return_pin_tip(pin_tip_device)

    if not pin_tip_valid(tip_xy_px):
        raise SampleException(
            "Pin tip centring failed - pin too long/short/bent and out of range"
        )
    else:
        return (int(tip_xy_px[0]), int(tip_xy_px[1]))


def pin_tip_centre_plan(
    composite: PinTipCentringComposite,
    tip_offset_microns: float,
    oav_config_file: str = OAV_CONFIG_JSON,
):
    """Finds the tip of the pin and moves to roughly the centre based on this tip. Does
    this at both the current omega angle and +90 deg from this angle so as to get a
    centre in 3D.

    Args:
        tip_offset_microns (float): The x offset from the tip where the centre is assumed
                                    to be.
    """
    oav: OAV = composite.oav
    smargon: Smargon = composite.smargon
    oav_params = OAVParameters("pinTipCentring", oav_config_file)

    pin_tip_setup = composite.pin_tip_detection
    pin_tip_detect = composite.pin_tip_detection

    microns_per_pixel_x = yield from bps.rd(oav.microns_per_pixel_x)
    tip_offset_px = int(tip_offset_microns / microns_per_pixel_x)

    def offset_and_move(tip: Pixel):
        pixel_to_move_to = (tip[0] + tip_offset_px, tip[1])
        position_mm = yield from get_move_required_so_that_beam_is_at_pixel(
            smargon, pixel_to_move_to, oav
        )
        LOGGER.info(f"Tip centring moving to : {position_mm}")
        yield from move_smargon_warn_on_out_of_range(smargon, position_mm)

    LOGGER.info(f"Tip offset in pixels: {tip_offset_px}")

    # need to wait for the OAV image to update
    # See #673 for improvements
    yield from bps.sleep(0.3)

    yield from pre_centring_setup_oav(oav, oav_params, pin_tip_setup)

    tip = yield from move_pin_into_view(pin_tip_detect, smargon)
    yield from offset_and_move(tip)

    yield from bps.mvr(smargon.omega, 90)

    # need to wait for the OAV image to update
    # See #673 for improvements
    yield from bps.sleep(0.3)
    tip = yield from catch_exception_and_warn(
        PinNotFoundException, wait_for_tip_to_be_found, pin_tip_detect
    )
    yield from offset_and_move(tip)
