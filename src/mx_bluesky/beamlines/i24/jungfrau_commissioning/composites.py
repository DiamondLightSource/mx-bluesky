from __future__ import annotations

import pydantic
from dodal.devices.attenuator.attenuator import EnumFilterAttenuator
from dodal.devices.hutch_shutter import HutchShutter
from dodal.devices.i24.aperture import Aperture
from dodal.devices.i24.beamstop import Beamstop
from dodal.devices.i24.commissioning_jungfrau import CommissioningJungfrau
from dodal.devices.i24.dcm import DCM
from dodal.devices.i24.dual_backlight import DualBacklight
from dodal.devices.i24.vgonio import VerticalGoniometer
from dodal.devices.motors import YZStage
from dodal.devices.synchrotron import Synchrotron
from dodal.devices.zebra.zebra import Zebra
from dodal.devices.zebra.zebra_controlled_shutter import ZebraShutter


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class RotationScanComposite:
    """All devices which are directly or indirectly required by this plan"""

    aperture: Aperture
    attenuator: EnumFilterAttenuator
    jungfrau: CommissioningJungfrau
    gonio: VerticalGoniometer
    synchrotron: Synchrotron
    sample_shutter: ZebraShutter
    zebra: Zebra
    # xbpm_feedback: XBPMFeedback
    hutch_shutter: HutchShutter
    beamstop: Beamstop
    det_stage: YZStage
    backlight: DualBacklight
    dcm: DCM
