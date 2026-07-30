from __future__ import annotations

from typing import Generic

import pydantic
from dodal.devices.aperturescatterguard import ApertureScatterguard
from dodal.devices.backlight import Backlight
from dodal.devices.detector.detector_motion import DetectorMotion
from dodal.devices.mx_phase1.beamstop import Beamstop
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.oav.pin_image_recognition import PinTipDetection
from dodal.devices.smargon import Smargon
from dodal.devices.synchrotron import Synchrotron
from dodal.devices.zocalo import ZocaloResults

from mx_bluesky.common.device_setup_plans.detector.beamline_specific import (
    TDetector,
)
from mx_bluesky.common.device_setup_plans.utils import DiffractionExtendedDevices

# MX gridscans only uses the gonio to set omega to 0. Other motors are only accessed in the motion program


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class OavGridDetectionComposite:
    """All devices which are directly or indirectly required by this plan"""

    backlight: Backlight
    oav: OAV
    gonio: Smargon
    pin_tip_detection: PinTipDetection


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class GridDetectAndGridScanExtendedDevices(
    DiffractionExtendedDevices[TDetector],
    OavGridDetectionComposite,
    Generic[TDetector],
):
    """The set of devices for running grid detection followed by a gridscan."""

    _detector: TDetector
    synchrotron: Synchrotron
    gonio: Smargon
    aperture_scatterguard: ApertureScatterguard
    beamstop: Beamstop
    detector_motion: DetectorMotion

    zocalo: ZocaloResults

    @property
    def detector(self) -> TDetector:
        return self._detector
