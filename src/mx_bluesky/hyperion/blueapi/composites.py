# TODO move this out of this package https://github.com/DiamondLightSource/mx-bluesky/issues/1793
from dataclasses import asdict
from typing import Generic

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
from dodal.devices.robot import BartRobot
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

from mx_bluesky.common.parameters.device_composites import (
    GridDetectAndGridScanEssentialDevices,
    TDetector,
)

# TODO replace this switch with a config server switch
use_fast_cs_eiger: bool = False


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class HyperionGridDetectThenXRayCentreComposite:
    """All devices which are directly or indirectly required by Hyperion Grid Detect and XRC plan"""

    aperture_scatterguard: ApertureScatterguard
    attenuator: BinaryFilterAttenuator
    backlight: Backlight
    beamsize: BeamsizeBase
    beamstop: Beamstop
    dcm: DoubleCrystalMonochromator
    detector_motion: DetectorMotion
    eiger: EigerDetector
    fast_cs_eiger: FastCSEiger
    flux: Flux
    gonio: Smargon
    oav: OAV
    panda: HDFPanda
    panda_fast_grid_scan: PandAFastGridScan
    pin_tip_detection: PinTipDetection
    robot: BartRobot
    s4_slit_gaps: S4SlitGaps
    sample_shutter: MXZebraShutter
    synchrotron: Synchrotron
    undulator: UndulatorInKeV
    xbpm_feedback: XBPMFeedback
    zebra: Zebra
    zebra_fast_grid_scan: ZebraFastGridScanThreeD
    zocalo: ZocaloResults


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class HyperionInternalGridDetectThenXRayCentreComposite(
    GridDetectAndGridScanEssentialDevices[TDetector], Generic[TDetector]
):
    attenuator: BinaryFilterAttenuator
    beamsize: BeamsizeBase
    dcm: DoubleCrystalMonochromator
    flux: Flux
    panda: HDFPanda
    panda_fast_grid_scan: PandAFastGridScan
    s4_slit_gaps: S4SlitGaps
    sample_shutter: MXZebraShutter
    undulator: UndulatorInKeV
    zebra: Zebra
    zebra_fast_grid_scan: ZebraFastGridScanThreeD


def create_detector_specific_composite(
    composite: HyperionGridDetectThenXRayCentreComposite,
) -> HyperionInternalGridDetectThenXRayCentreComposite:
    kwargs = asdict(composite)
    kwargs["detector"] = (
        kwargs["fast_cs_eiger"] if use_fast_cs_eiger else kwargs["eiger"]
    )
    return HyperionInternalGridDetectThenXRayCentreComposite(**kwargs)
