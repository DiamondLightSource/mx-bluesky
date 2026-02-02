from collections.abc import Callable
from typing import Any, Literal

import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.common import inject
from dodal.devices.aperturescatterguard import (
    ApertureScatterguard,
)
from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
from dodal.devices.backlight import Backlight
from dodal.devices.baton import Baton
from dodal.devices.detector.detector_motion import DetectorMotion
from dodal.devices.diamond_filter import DiamondFilter, I04Filters
from dodal.devices.fast_grid_scan import ZebraFastGridScanThreeD
from dodal.devices.flux import Flux
from dodal.devices.i03.dcm import DCM
from dodal.devices.i04.beam_centre import CentreEllipseMethod
from dodal.devices.i04.beamsize import Beamsize
from dodal.devices.i04.max_pixel import MaxPixel
from dodal.devices.i04.murko_results import MurkoResultsDevice
from dodal.devices.i04.transfocator import Transfocator
from dodal.devices.ipin import IPin
from dodal.devices.motors import XYZStage
from dodal.devices.mx_phase1.beamstop import Beamstop
from dodal.devices.oav.oav_detector import (
    OAVBeamCentrePV,
)
from dodal.devices.oav.pin_image_recognition import PinTipDetection
from dodal.devices.robot import BartRobot
from dodal.devices.s4_slit_gaps import S4SlitGaps
from dodal.devices.scintillator import Scintillator
from dodal.devices.smargon import Smargon
from dodal.devices.synchrotron import Synchrotron
from dodal.devices.thawer import Thawer
from dodal.devices.undulator import UndulatorInKeV
from dodal.devices.xbpm_feedback import XBPMFeedback
from dodal.devices.zebra.zebra import Zebra
from dodal.devices.zebra.zebra_controlled_shutter import ZebraShutter
from dodal.devices.zocalo import ZocaloResults

from mx_bluesky.common.utils.log import LOGGER

PLAN_NAME = Literal["mv", "rd"]
NAME_TO_PLAN_MAP: dict[PLAN_NAME, Callable[..., MsgGenerator]] = {
    "mv": bps.mv,
    "rd": bps.rd,
}


def do_plan_stup(
    plan: PLAN_NAME,
    device: str,
    value: Any = None,
    smargon: Smargon = inject("smargon"),
    gonio_positioner: XYZStage = inject("gonio_positioner"),
    sample_delivery_system: XYZStage = inject("sample_delivery_system"),
    ipin: IPin = inject("ipin"),
    beamstop: Beamstop = inject("beamstop"),
    sample_shutter: ZebraShutter = inject("sample_shutter"),
    attenuator: BinaryFilterAttenuator = inject("attenuator"),
    transfocator: Transfocator = inject("transfocator"),
    baton: Baton = inject("baton"),
    xbpm_feedback: XBPMFeedback = inject("xbpm_feedback"),
    flux: Flux = inject("flux"),
    dcm: DCM = inject("dcm"),
    backlight: Backlight = inject("backlight"),
    aperture_scatterguard: ApertureScatterguard = inject("aperture_scatterguard"),
    zebra_fast_grid_scan: ZebraFastGridScanThreeD = inject("zebra_fast_grid_scan"),
    s4_slit_gaps: S4SlitGaps = inject("s4_slit_gaps"),
    undulator: UndulatorInKeV = inject("undulator"),
    synchrotron: Synchrotron = inject("synchrotron"),
    zebra: Zebra = inject("zebra"),
    oav: OAVBeamCentrePV = inject("oav"),
    oav_full_screen: OAVBeamCentrePV = inject("oav_full_screen"),
    detector_motion: DetectorMotion = inject("detector_motion"),
    thawer: Thawer = inject("thawer"),
    robot: BartRobot = inject("robot"),
    murko_results: MurkoResultsDevice = inject("murko_results"),
    diamond_filter: DiamondFilter[I04Filters] = inject("diamond_filter"),
    zocalo: ZocaloResults = inject("zocalo"),
    pin_tip_detection: PinTipDetection = inject("pin_tip_detection"),
    scintillator: Scintillator = inject("scintillator"),
    max_pixel: MaxPixel = inject("max_pixel"),
    beamsize: Beamsize = inject("beamsize"),
    beam_centre: CentreEllipseMethod = inject("beam_centre"),
):
    devices = {
        "smargon": smargon,
        "gonio_positioner": gonio_positioner,
        "sample_delivery_system": sample_delivery_system,
        "ipin": ipin,
        "beamstop": beamstop,
        "sample_shutter": sample_shutter,
        "attenuator": attenuator,
        "transfocator": transfocator,
        "baton": baton,
        "xbpm_feedback": xbpm_feedback,
        "flux": flux,
        "dcm": dcm,
        "backlight": backlight,
        "aperture_scatterguard": aperture_scatterguard,
        "zebra_fast_grid_scan": zebra_fast_grid_scan,
        "s4_slit_gaps": s4_slit_gaps,
        "undulator": undulator,
        "synchrotron": synchrotron,
        "zebra": zebra,
        "oav": oav,
        "oav_full_screen": oav_full_screen,
        "detector_motion": detector_motion,
        "thawer": thawer,
        "robot": robot,
        "murko_results": murko_results,
        "diamond_filter": diamond_filter,
        "zocalo": zocalo,
        "pin_tip_detection": pin_tip_detection,
        "scintillator": scintillator,
        "max_pixel": max_pixel,
        "beamsize": beamsize,
        "beam_centre": beam_centre,
    }
    yield from NAME_TO_PLAN_MAP[plan](devices[device], value)
    LOGGER.info("Done!")


def read_device(device: str):
    device = inject(device)
    value = yield from bps.rd(device)
    LOGGER.info(f"Read {device}, got {value}.")
