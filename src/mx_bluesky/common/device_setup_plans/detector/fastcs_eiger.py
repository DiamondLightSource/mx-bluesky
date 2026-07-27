from collections.abc import Sequence
from typing import Any

from bluesky import plan_stubs as bps
from bluesky.protocols import Readable
from bluesky.utils import MsgGenerator
from event_model import Event

from dodal.devices.detector import DetectorParams
from dodal.plans.configure_arm_trigger_and_disarm_detector import configure_and_arm_detector
from mx_bluesky.common.external_interaction.callbacks.common.zocalo_callback import ZocaloHWReadPayload
from mx_bluesky.common.external_interaction.callbacks.grid.grid_detect_and_scan.event_mapping import \
    HWReadDuringPayload
from mx_bluesky.common.parameters.device_composites import FlyScanEssentialDevices
from ophyd_async.core import TriggerInfo, DetectorTrigger
from ophyd_async.fastcs.eiger import EigerDetector


def fastcs_eiger_pre_arm(
        device_composite: FlyScanEssentialDevices[Any, EigerDetector],
        detector_params: DetectorParams,
        group: str
) -> MsgGenerator:
    yield from configure_and_arm_detector(
        eiger=device_composite.detector,
        detector_params=detector_params,
        trigger_info=TriggerInfo(
            number_of_events=detector_params.num_images_per_trigger,
            trigger=DetectorTrigger.EXTERNAL_EDGE,
            deadtime=0.0001,
        ),
        group=group
    )


def fastcs_eiger_arm(device_composite: FlyScanEssentialDevices[Any, EigerDetector],
                     detector_params: DetectorParams,
                     group: str) -> MsgGenerator:
    yield from bps.kickoff(device_composite.detector, group=group)


def fastcs_eiger_disarm(device_composite: FlyScanEssentialDevices[Any, EigerDetector]) -> MsgGenerator:
    yield from bps.complete(device_composite.detector, wait=True)


def fastcs_eiger_zocalo_hw_read_signals(eiger: EigerDetector) -> Sequence[Readable]:
    # TODO update for FastCS Odin
    return [eiger.odin.id]


def fastcs_eiger_zocalo_hw_read_mapper(doc: Event) -> ZocaloHWReadPayload:
    # TODO
    ...


def fastcs_eiger_hw_read_during_signals(eiger: EigerDetector) -> Sequence[Readable]:
    return [
        eiger.detector.bit_depth_image
    ]


def fastcs_eiger_hw_read_during_mapper(doc: Event) -> HWReadDuringPayload:
    return HWReadDuringPayload(
        bit_depth=doc["data"]["eiger-detector-bit_depth_image"]
    )


def fastcs_eiger_tidy(device_composite: FlyScanEssentialDevices[Any, EigerDetector]) -> MsgGenerator:
    # TODO disable dev_shm for fastcs odin
    yield from bps.null()