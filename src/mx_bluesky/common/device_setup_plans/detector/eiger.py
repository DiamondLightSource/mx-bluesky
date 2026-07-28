"""
Detector-specific logic for setting up the classic ophyd eiger
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from bluesky import plan_stubs as bps
from bluesky.protocols import Readable
from bluesky.utils import MsgGenerator
from dodal.devices.detector import DetectorParams
from dodal.devices.eiger import EigerDetector
from event_model import Event

from mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan import (
    BeamlineSpecificDetectorFeatures,
)
from mx_bluesky.common.external_interaction.callbacks.common.zocalo_callback import (
    ZocaloHWReadPayload,
)
from mx_bluesky.common.external_interaction.callbacks.grid.grid_detect_and_scan.event_mapping import (
    HWReadDuringPayload,
)
from mx_bluesky.common.parameters.device_composites import DiffractionEssentialDevices
from mx_bluesky.common.utils.log import LOGGER


def create_eiger_beamline_specific(
    eiger: EigerDetector,
) -> BeamlineSpecificDetectorFeatures:
    return BeamlineSpecificDetectorFeatures(
        pre_arm_detector_plan=eiger_pre_arm,
        arm_detector_plan=eiger_arm,
        disarm_detector_plan=eiger_disarm,
        tidy_detector_plan=eiger_tidy,
        detector_zocalo_hw_read_signals=eiger_zocalo_hw_read_signals(eiger),
        detector_hw_read_during_signals=eiger_hw_read_during_signals(eiger),
    )


def eiger_pre_arm(
    device_composite: DiffractionEssentialDevices[Any, EigerDetector],
    detector_params: DetectorParams,
    group: str,
) -> MsgGenerator:
    device_composite.detector.set_detector_parameters(detector_params)
    yield from bps.abs_set(eiger.do_arm, 1, group=group)  # type: ignore # Fix types in ophyd-async (https://github.com/DiamondLightSource/mx-bluesky/issues/855)


def eiger_arm(
    device_composite: DiffractionEssentialDevices[Any, EigerDetector],
    detector_params: DetectorParams,
    group: str,
) -> MsgGenerator:
    yield from bps.stage(device_composite.detector, group=group)


def eiger_disarm(
    device_composite: DiffractionEssentialDevices[Any, EigerDetector],
) -> MsgGenerator:
    yield from bps.unstage(device_composite.detector, wait=True)


def eiger_zocalo_hw_read_signals(eiger: EigerDetector) -> Sequence[Readable]:
    return [eiger.odin_file_writer.id]


def eiger_zocalo_hw_read_mapper(doc: Event) -> ZocaloHWReadPayload:
    return ZocaloHWReadPayload(file_name=doc["data"]["eiger_odin_file_writer_id"])


def eiger_hw_read_during_signals(eiger: EigerDetector) -> Sequence:
    return [
        eiger.cam.roi_mode,
        eiger.ispyb_detector_id,
        eiger.bit_depth,
    ]


def eiger_hw_read_during_mapper(doc: Event) -> HWReadDuringPayload:
    return HWReadDuringPayload(
        bit_depth=doc["data"]["eiger_bit_depth"],
        ispyb_detector_id=doc["data"]["eiger-ispyb_detector_id"],
        roi_mode=bool(doc["data"]["eiger-cam-roi_mode"]),
    )


def eiger_tidy(
    device_composite: DiffractionEssentialDevices[Any, EigerDetector],
) -> MsgGenerator:
    """Turn off Eiger dev/shm. Ran after the beamline-specific tidy plan"""

    # Turn off dev/shm streaming to avoid filling disk, see https://github.com/DiamondLightSource/hyperion/issues/1395
    LOGGER.info("Turning off Eiger dev/shm streaming")
    # Fix types in ophyd-async (https://github.com/DiamondLightSource/mx-bluesky/issues/855)
    yield from bps.abs_set(
        device_composite.detector.odin.fan.dev_shm_enable,  # type: ignore # until https://github.com/DiamondLightSource/mx-bluesky/issues/1076
        0,
        wait=True,
    )
