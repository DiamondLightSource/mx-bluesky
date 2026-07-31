from __future__ import annotations

import pydantic
from dodal.devices.attenuator.attenuator import EnumFilterAttenuator
from dodal.devices.beamlines.i24.aperture import Aperture
from dodal.devices.beamlines.i24.beamstop import Beamstop
from dodal.devices.beamlines.i24.commissioning_jungfrau import (
    CommissioningJungfrauDetector,
)
from dodal.devices.beamlines.i24.dcm import DCM
from dodal.devices.beamlines.i24.dual_backlight import DualBacklight
from dodal.devices.beamlines.i24.vgonio import VerticalGoniometer
from dodal.devices.hutch_shutter import InterlockedHutchShutter
from dodal.devices.motors import YZStage
from dodal.devices.synchrotron import Synchrotron
from dodal.devices.zebra.zebra import Zebra
from dodal.devices.zebra.zebra_controlled_shutter import MXZebraShutter


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class RotationScanComposite:
    """All devices which are directly or indirectly required by this plan"""

    aperture: Aperture
    attenuator: EnumFilterAttenuator
    jungfrau: CommissioningJungfrauDetector
    vgonio: VerticalGoniometer
    synchrotron: Synchrotron
    sample_shutter: MXZebraShutter
    zebra: Zebra
    # xbpm_feedback: XBPMFeedback # Not referenced
    shutter: InterlockedHutchShutter
    beamstop: Beamstop
    detector_motion: YZStage
    backlight: DualBacklight
    dcm: DCM
