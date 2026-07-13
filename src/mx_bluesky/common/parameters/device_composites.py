from __future__ import annotations

from typing import Generic, Protocol, TypeVar, runtime_checkable

import pydantic
from dodal.devices.aperturescatterguard import ApertureScatterguard
from dodal.devices.backlight import Backlight
from dodal.devices.detector.detector_motion import DetectorMotion
from dodal.devices.eiger import EigerDetector
from dodal.devices.mx_phase1.beamstop import Beamstop
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.oav.pin_image_recognition import PinTipDetection
from dodal.devices.smargon import Smargon
from dodal.devices.synchrotron import Synchrotron
from dodal.devices.wrapped_axis import WrappedAxis
from dodal.devices.zocalo import ZocaloResults
from ophyd_async.epics.motor import Motor


# MX gridscans only uses the gonio to set omega to 0. Other motors are only accessed in the motion program
@runtime_checkable
class GonioWithOmega(Protocol):
    omega: Motor
    wrapped_omega: WrappedAxis


GonioWithOmegaType = TypeVar("GonioWithOmegaType", bound=GonioWithOmega)


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class FlyScanEssentialDevices(Generic[GonioWithOmegaType]):
    eiger: EigerDetector
    synchrotron: Synchrotron
    gonio: GonioWithOmegaType


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class OavGridDetectionComposite:
    """All devices which are directly or indirectly required by this plan"""

    backlight: Backlight
    oav: OAV
    gonio: Smargon
    pin_tip_detection: PinTipDetection


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class GridDetectAndGridScanEssentialDevices(
    FlyScanEssentialDevices[Smargon], OavGridDetectionComposite
):
    aperture_scatterguard: ApertureScatterguard
    beamstop: Beamstop
    detector_motion: DetectorMotion
    zocalo: ZocaloResults
