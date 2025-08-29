from typing import Generic, Protocol, TypeVar, runtime_checkable

import pydantic
from dodal.devices.aperturescatterguard import (
    ApertureScatterguard,
)
from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
from dodal.devices.backlight import Backlight
from dodal.devices.common_dcm import BaseDCM
from dodal.devices.detector.detector_motion import DetectorMotion
from dodal.devices.eiger import EigerDetector
from dodal.devices.fast_grid_scan import (
    FastGridScanCommon,
    GridScanParamsCommon,
    GridScanParamsThreeD,
)
from dodal.devices.flux import Flux
from dodal.devices.mx_phase1.beamstop import Beamstop
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.oav.pin_image_recognition import PinTipDetection
from dodal.devices.robot import BartRobot
from dodal.devices.s4_slit_gaps import S4SlitGaps
from dodal.devices.smargon import Smargon
from dodal.devices.synchrotron import Synchrotron
from dodal.devices.undulator import Undulator
from dodal.devices.xbpm_feedback import XBPMFeedback
from dodal.devices.zebra.zebra import Zebra
from dodal.devices.zebra.zebra_controlled_shutter import ZebraShutter
from dodal.devices.zocalo import ZocaloResults
from ophyd_async.epics.motor import Motor

# FGS plan only uses the gonio to set omega to 0, no need to constrain to a more complex device


@runtime_checkable
class SampleStageWithOmega(Protocol):
    omega: Motor


GridScanParamType = TypeVar(
    "GridScanParamType", bound=GridScanParamsCommon, covariant=True
)

# Smargon is required in plans which move crystal post-gridscan or require stub-offsets
MotorType = TypeVar("MotorType")


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class FlyScanBaseComposite(Generic[GridScanParamType, MotorType]):
    eiger: EigerDetector
    synchrotron: Synchrotron
    sample_stage: MotorType
    grid_scan: FastGridScanCommon[GridScanParamType]


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class OavGridDetectionComposite:
    """All devices which are directly or indirectly required by this plan"""

    backlight: Backlight
    oav: OAV
    smargon: Smargon
    pin_tip_detection: PinTipDetection


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class GridDetectThenXRayCentreComposite(
    FlyScanBaseComposite[GridScanParamsThreeD, Smargon]
):
    """All devices which are directly or indirectly required by this plan"""

    aperture_scatterguard: ApertureScatterguard
    attenuator: BinaryFilterAttenuator
    backlight: Backlight
    beamstop: Beamstop
    dcm: BaseDCM
    detector_motion: DetectorMotion
    flux: Flux
    oav: OAV
    pin_tip_detection: PinTipDetection
    s4_slit_gaps: S4SlitGaps
    undulator: Undulator
    xbpm_feedback: XBPMFeedback
    zebra: Zebra
    robot: BartRobot
    sample_shutter: ZebraShutter
    zocalo: ZocaloResults
