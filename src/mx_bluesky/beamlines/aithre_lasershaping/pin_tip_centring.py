from bluesky.utils import MsgGenerator
from dodal.common import inject
from dodal.devices.aithre_lasershaping.goniometer import Goniometer
from dodal.devices.backlight import Backlight
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.oav.pin_image_recognition import PinTipDetection

from mx_bluesky.beamlines.aithre_lasershaping.parameters.constants import CONST
from mx_bluesky.common.experiment_plans.pin_tip_centring_plan import (
    PinTipCentringComposite,
    pin_tip_centre_plan,
)


def aithre_pin_tip_centre(
    backlight: Backlight = inject("backlight"),
    oav: OAV = inject("OAV"),
    gonio: Goniometer = inject("gonio"),
    pin_tip_detection: PinTipDetection = inject("pin_tip_detection"),
    tip_offset_microns: float = 0,
    oav_config_file: str = CONST.OAV_CENTRING_FILE,
) -> MsgGenerator:
    """
    A plan that use pin_tip_centre_plan from common for aithre
    """

    composite = PinTipCentringComposite(backlight, oav, gonio, pin_tip_detection)

    yield from pin_tip_centre_plan(
        composite=composite,
        tip_offset_microns=tip_offset_microns,
        oav_config_file=oav_config_file,
    )
