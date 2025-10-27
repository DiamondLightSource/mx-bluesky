"""
Utilities for defining the detector in use, and moving the stage.
"""

from collections.abc import Generator
from enum import IntEnum

import bluesky.plan_stubs as bps
from bluesky.utils import Msg, MsgGenerator
from dodal.common import inject
from dodal.devices.motors import YZStage

from mx_bluesky.beamlines.i24.serial.log import SSX_LOGGER
from mx_bluesky.beamlines.i24.serial.parameters import SSXType
from mx_bluesky.beamlines.i24.serial.setup_beamline import pv
from mx_bluesky.beamlines.i24.serial.setup_beamline.ca import caget, caput
from mx_bluesky.beamlines.i24.serial.setup_beamline.pv_abstract import (
    Detector,
    Eiger,
)

EXPT_TYPE_DETECTOR_PVS = {
    SSXType.FIXED: pv.me14e_gp101,
    SSXType.EXTRUDER: pv.ioc13_gp15,
}


class DetRequest(IntEnum):
    eiger = 0

    def __str__(self) -> str:
        return self.name


class UnknownDetectorTypeError(Exception):
    pass


def get_detector_type(detector_stage: YZStage) -> Generator[Msg, None, Detector]:
    det_y = yield from bps.rd(detector_stage.y)
    # YZStage should also be used for this.
    # This should be part of https://github.com/DiamondLightSource/mx_bluesky/issues/51
    if float(det_y) < Eiger.det_y_threshold:
        SSX_LOGGER.info("Eiger detector in use.")
        return Eiger()
    else:
        SSX_LOGGER.error("Detector not found.")
        raise UnknownDetectorTypeError("Detector not found.")


def _move_detector_stage(detector_stage: YZStage, target: float) -> MsgGenerator:
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
        str: The detector name as a string, currently "eiger".
    """
    det_type = caget(det_type_pv)
    if det_type in ["eiger"]:
        return det_type
    else:
        try:
            det_type = int(det_type)
            return str(DetRequest(det_type))
        except ValueError:
            raise


def setup_detector_stage(
    expt_type: SSXType, detector_stage: YZStage = inject("detector_motion")
) -> MsgGenerator:
    # Grab the correct PV depending on experiment
    # Its value is set with MUX on edm screen
    det_type_pv = EXPT_TYPE_DETECTOR_PVS[expt_type]
    requested_detector = _get_requested_detector(det_type_pv)
    SSX_LOGGER.info(f"Requested detector: {requested_detector}.")
    det_y_target = Eiger.det_y_target

    yield from _move_detector_stage(detector_stage, det_y_target)
    caput(det_type_pv, requested_detector)
    SSX_LOGGER.info("Detector setup done.")
