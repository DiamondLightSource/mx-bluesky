import pydantic
from bluesky.utils import MsgGenerator
from dodal.common import inject
from dodal.devices.aperturescatterguard import ApertureScatterguard
from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
from dodal.devices.backlight import Backlight
from dodal.devices.dcm import DCM
from dodal.devices.detector.detector_motion import DetectorMotion
from dodal.devices.eiger import EigerDetector
from dodal.devices.fast_grid_scan import PandAFastGridScan, ZebraFastGridScan
from dodal.devices.flux import Flux
from dodal.devices.motors import XYZPositioner
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
from ophyd_async.fastcs.panda import HDFPanda

from mx_bluesky.common.parameters.constants import OavConstants
from mx_bluesky.hyperion.experiment_plans.grid_detect_then_xray_centre_plan import (
    GridDetectThenXRayCentreCompositeProtocol,
)
from mx_bluesky.hyperion.experiment_plans.grid_detect_then_xray_centre_plan import (
    grid_detect_then_xray_centre as grid_detect_then_xray_centre_hyperion,
)
from mx_bluesky.hyperion.parameters.gridscan import GridScanWithEdgeDetect


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class I04GridDetectThenXRayCentreComposite(GridDetectThenXRayCentreCompositeProtocol):
    """All devices which are directly or indirectly required by this plan"""

    aperture_scatterguard: ApertureScatterguard
    attenuator: BinaryFilterAttenuator
    backlight: Backlight
    beamstop: XYZPositioner
    dcm: DCM
    detector_motion: DetectorMotion
    eiger: EigerDetector
    zebra_fast_grid_scan: ZebraFastGridScan
    flux: Flux
    oav: OAV
    pin_tip_detection: PinTipDetection
    smargon: Smargon
    synchrotron: Synchrotron
    s4_slit_gaps: S4SlitGaps
    undulator: Undulator
    xbpm_feedback: XBPMFeedback
    zebra: Zebra
    zocalo: ZocaloResults
    panda: HDFPanda
    panda_fast_grid_scan: PandAFastGridScan
    robot: BartRobot
    sample_shutter: ZebraShutter


def grid_detect_then_xray_centre(
    parameters: GridScanWithEdgeDetect,
    oav_config: str = OavConstants.OAV_CONFIG_JSON,
    aperture_scatterguard: ApertureScatterguard = inject("aperture_scatterguard"),
    attenuator: BinaryFilterAttenuator = inject("attenuator"),
    backlight: Backlight = inject("backlight"),
    beamstop: XYZPositioner = inject("beamstop"),
    dcm: DCM = inject("dcm"),
    detector_motion: DetectorMotion = inject("detector_motion"),
    eiger: EigerDetector = inject("eiger"),
    zebra_fast_grid_scan: ZebraFastGridScan = inject("zebra_fast_grid_scan"),
    flux: Flux = inject("flux"),
    oav: OAV = inject("oav"),
    pin_tip_detection: PinTipDetection = inject("pin_tip_detection"),
    smargon: Smargon = inject("smargon"),
    synchrotron: Synchrotron = inject("synchrotron"),
    s4_slit_gaps: S4SlitGaps = inject("s4_slit_gaps"),
    undulator: Undulator = inject("undulator"),
    xbpm_feedback: XBPMFeedback = inject("xbpm_feedback"),
    zebra: Zebra = inject("zebra"),
    zocalo: ZocaloResults = inject("zocalo"),
    panda: HDFPanda = inject("panda"),
    panda_fast_grid_scan: PandAFastGridScan = inject("panda_fast_grid_scan"),
    robot: BartRobot = inject("robot"),
    sample_shutter: ZebraShutter = inject("sample_shutter"),
) -> MsgGenerator:
    composite = I04GridDetectThenXRayCentreComposite(
        aperture_scatterguard=aperture_scatterguard,
        attenuator=attenuator,
        backlight=backlight,
        beamstop=beamstop,
        dcm=dcm,
        detector_motion=detector_motion,
        eiger=eiger,
        zebra_fast_grid_scan=zebra_fast_grid_scan,
        flux=flux,
        oav=oav,
        pin_tip_detection=pin_tip_detection,
        smargon=smargon,
        synchrotron=synchrotron,
        s4_slit_gaps=s4_slit_gaps,
        undulator=undulator,
        xbpm_feedback=xbpm_feedback,
        zebra=zebra,
        zocalo=zocalo,
        panda=panda,
        panda_fast_grid_scan=panda_fast_grid_scan,
        robot=robot,
        sample_shutter=sample_shutter,
    )
    yield from grid_detect_then_xray_centre_hyperion(composite, parameters, oav_config)


# def create_devices():
#     composite = I04GridDetectThenXRayCentreComposite(
#         aperture_scatterguard=aperture_scatterguard(),
#         attenuator=attenuator(),
#         backlight=backlight(),
#         beamstop=beamstop(),
#         dcm=dcm(),
#         detector_motion=detector_motion(),
#         eiger=eiger(),
#         zebra_fast_grid_scan=zebra_fast_grid_scan(),
#         flux=flux(),
#         oav=oav(),
#         pin_tip_detection=pin_tip_detection(),
#         smargon=smargon(),
#         synchrotron=synchrotron(),
#         s4_slit_gaps=s4_slit_gaps(),
#         undulator=undulator(),
#         xbpm_feedback=xbpm_feedback(),
#         zebra=zebra(),
#         zocalo=zocalo(),
#         robot=robot(),
#         sample_shutter=sample_shutter(),
#     )
#     return composite
