from typing import Generic, cast

import pydantic
from dodal.devices.aperturescatterguard import ApertureScatterguard
from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
from dodal.devices.backlight import Backlight
from dodal.devices.beamsize.beamsize import BeamsizeBase
from dodal.devices.common_dcm import DoubleCrystalMonochromator
from dodal.devices.detector.detector_motion import DetectorMotion
from dodal.devices.eiger import EigerDetector
from dodal.devices.fast_grid_scan import PandAFastGridScan, ZebraFastGridScanThreeD
from dodal.devices.flux import Flux
from dodal.devices.mx_phase1.beamstop import Beamstop
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.oav.pin_image_recognition import PinTipDetection
from dodal.devices.s4_slit_gaps import S4SlitGaps
from dodal.devices.smargon import Smargon
from dodal.devices.synchrotron import Synchrotron
from dodal.devices.undulator import UndulatorInKeV
from dodal.devices.xbpm_feedback import XBPMFeedback
from dodal.devices.zebra.zebra import Zebra
from dodal.devices.zebra.zebra_controlled_shutter import MXZebraShutter
from dodal.devices.zocalo import ZocaloResults
from ophyd_async.fastcs.eiger import EigerDetector as FastCSEiger
from ophyd_async.fastcs.panda import HDFPanda

from mx_bluesky.common.device_setup_plans.detector.beamline_specific import TDetector
from mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan import (
    GridDetectAndGridScanExtendedDevices,
)

# TODO replace this switch with a config server switch
use_fast_cs_eiger: bool = False


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class HyperionGridDetectThenXRayCentreComposite(
    GridDetectAndGridScanExtendedDevices[TDetector], Generic[TDetector]
):
    """All devices which are directly or indirectly required by Hyperion Grid Detect and XRC plan"""

    # Required to implement GridDetectAndGridScanExtendedDevices
    aperture_scatterguard: ApertureScatterguard
    backlight: Backlight
    beamstop: Beamstop
    detector_motion: DetectorMotion
    gonio: Smargon
    oav: OAV
    pin_tip_detection: PinTipDetection
    synchrotron: Synchrotron
    zocalo: ZocaloResults

    # Additional devices for sample environment, beam
    attenuator: BinaryFilterAttenuator
    beamsize: BeamsizeBase
    dcm: DoubleCrystalMonochromator
    flux: Flux
    s4_slit_gaps: S4SlitGaps
    sample_shutter: MXZebraShutter
    undulator: UndulatorInKeV
    xbpm_feedback: XBPMFeedback

    # Available detectors
    eiger: EigerDetector
    fastcs_eiger: FastCSEiger

    # Available gridscan devices
    panda: HDFPanda
    panda_fast_grid_scan: PandAFastGridScan
    zebra: Zebra
    zebra_fast_grid_scan: ZebraFastGridScanThreeD

    @property
    def detector(self) -> TDetector:
        return cast(TDetector, self.fastcs_eiger if use_fast_cs_eiger else self.eiger)
