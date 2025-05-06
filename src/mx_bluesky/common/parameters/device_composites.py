import pydantic
from dodal.devices.backlight import Backlight
from dodal.devices.eiger import EigerDetector
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.oav.pin_image_recognition import PinTipDetection
from dodal.devices.smargon import Smargon
from dodal.devices.synchrotron import Synchrotron
from dodal.devices.zocalo import ZocaloResults


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class FlyScanEssentialDevices:
    eiger: EigerDetector
    synchrotron: Synchrotron
    zocalo: ZocaloResults
    smargon: Smargon


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class OavGridDetectionComposite:
    """All devices which are directly or indirectly required by this plan"""

    backlight: Backlight
    oav: OAV
    smargon: Smargon
    pin_tip_detection: PinTipDetection
