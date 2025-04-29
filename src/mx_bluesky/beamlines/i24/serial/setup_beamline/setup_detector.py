"""
Utilities for defining the detector in use, and moving the stage.
"""

from collections.abc import Generator
from enum import IntEnum

import bluesky.plan_stubs as bps
from bluesky.utils import Msg, MsgGenerator
from dodal.common import inject
from dodal.devices.i24.i24_detector_motion import DetectorMotion

from mx_bluesky.beamlines.i24.serial.log import SSX_LOGGER
from mx_bluesky.beamlines.i24.serial.parameters import SSXType
from mx_bluesky.beamlines.i24.serial.setup_beamline import pv
from mx_bluesky.beamlines.i24.serial.setup_beamline.ca import caget, caput
from mx_bluesky.beamlines.i24.serial.setup_beamline.pv_abstract import (
    Detector,
    Eiger,
    Pilatus,
)

EXPT_TYPE_DETECTOR_PVS = {
    SSXType.FIXED: pv.me14e_gp101,
    SSXType.EXTRUDER: pv.ioc13_gp15,
}


class DetRequest(IntEnum):
    eiger = 0
    pilatus = 1

    def __str__(self) -> str:
        return self.name


class UnknownDetectorType(Exception):
    pass


def get_detector_type(detector_stage: DetectorMotion) -> Generator[Msg, None, Detector]:
    det_y = yield from bps.rd(detector_stage.y)
    # DetectorMotion should also be used for this.
    # This should be part of https://github.com/DiamondLightSource/mx_bluesky/issues/51
    if float(det_y) < Eiger.det_y_threshold:
        SSX_LOGGER.info("Eiger detector in use.")
        return Eiger()
    elif float(det_y) > Pilatus.det_y_threshold:
        SSX_LOGGER.info("Pilatus detector in use.")
        return Pilatus()
    else:
        SSX_LOGGER.error("Detector not found.")
        raise UnknownDetectorType("Detector not found.")


def _move_detector_stage(detector_stage: DetectorMotion, target: float) -> MsgGenerator:
    SSX_LOGGER.info(f"Moving detector stage to target position: {target}.")
    yield from bps.mv(detector_stage.y, target)


# Workaround in case the PV value has been set to the detector name
def _get_requested_detector(det_type_pv: str) -> str:
    """Get the requested detector name from the PV value.

    Args:
        det_type_pv (str): PV associated to the detector request. This is usually a \
            general purpose PV set up for the serial collection which could contain \
            a string or and int.

    Returns:
        str: The detector name as a string, currently "eiger" or "pilatus".
    """
    det_type = caget(det_type_pv)
    if det_type in ["pilatus", "eiger"]:
        return det_type
    else:
        try:
            det_type = int(det_type)
            return str(DetRequest(det_type))
        except ValueError:
            raise


def setup_detector_stage(
    expt_type: SSXType, detector_stage: DetectorMotion = inject("detector_motion")
) -> MsgGenerator:
    # Grab the correct PV depending on experiment
    # Its value is set with MUX on edm screen
    det_type_pv = EXPT_TYPE_DETECTOR_PVS[expt_type]
    requested_detector = _get_requested_detector(det_type_pv)
    SSX_LOGGER.info(f"Requested detector: {requested_detector}.")
    det_y_target = (
        Eiger.det_y_target if requested_detector == "eiger" else Pilatus.det_y_target
    )
    yield from _move_detector_stage(detector_stage, det_y_target)
    caput(det_type_pv, requested_detector)
    SSX_LOGGER.info("Detector setup done.")
