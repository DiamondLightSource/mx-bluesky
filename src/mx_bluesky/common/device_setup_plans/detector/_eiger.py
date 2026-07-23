"""
Detector-specific logic for setting up the classic ophyd eiger
"""

from bluesky import plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.devices.detector import DetectorParams
from dodal.devices.detector.detector_motion import DetectorMotion, ShutterState
from dodal.devices.eiger import EigerDetector

from mx_bluesky.common.device_setup_plans.position_detector import (
    set_detector_z_position,
    set_shutter,
)


def eiger_pre_arm(
    eiger: EigerDetector,
    detector_motion: DetectorMotion,
    detector_params: DetectorParams,
    group: str,
) -> MsgGenerator:
    eiger.set_detector_parameters(detector_params)
    yield from bps.abs_set(eiger.do_arm, 1, group=group)  # type: ignore # Fix types in ophyd-async (https://github.com/DiamondLightSource/mx-bluesky/issues/855)
    if detector_distance_mm:
        yield from set_detector_z_position(detector_motion, detector_distance_mm, group)
    yield from set_shutter(detector_motion, ShutterState.OPEN, group)
    yield from plan_to_run
