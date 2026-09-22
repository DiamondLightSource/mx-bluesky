from collections.abc import Sequence
from typing import Any

from bluesky import plan_stubs as bps
from bluesky.protocols import Readable
from bluesky.utils import MsgGenerator
from dodal.devices.detector import DetectorParams
from dodal.plans.configure_arm_trigger_and_disarm_detector import (
    configure_and_arm_detector,
)
from event_model import Event
from ophyd_async.core import DetectorTrigger, TriggerInfo
from ophyd_async.fastcs.eiger import EigerDetector

from mx_bluesky.common.device_setup_plans.detector.beamline_specific import (
    BeamlineSpecificDetectorFeatures,
    DiffractionEssentialDevices,
)
from mx_bluesky.common.external_interaction.callbacks.common.zocalo_callback import (
    ZocaloHWReadPayload,
)
from mx_bluesky.common.external_interaction.callbacks.grid.grid_detect_and_scan.event_mapping import (
    HWReadDuringPayload,
)


def create_fastcs_eiger_beamline_specific(
    eiger: EigerDetector,
) -> BeamlineSpecificDetectorFeatures:
    return BeamlineSpecificDetectorFeatures(
        pre_arm_detector_plan=fastcs_eiger_pre_arm,
        arm_detector_plan=fastcs_eiger_arm,
        disarm_detector_plan=fastcs_eiger_disarm,
        tidy_detector_plan=fastcs_eiger_tidy,
        detector_zocalo_hw_read_signals=fastcs_eiger_zocalo_hw_read_signals(eiger),
        detector_hw_read_during_signals=fastcs_eiger_hw_read_during_signals(eiger),
    )


def fastcs_eiger_pre_arm(
    device_composite: DiffractionEssentialDevices[Any, EigerDetector],
    detector_params: DetectorParams,
    group: str,
) -> MsgGenerator:
    yield from configure_and_arm_detector(
        eiger=device_composite.detector,
        detector_params=detector_params,
        trigger_info=TriggerInfo(
            number_of_events=detector_params.num_images_per_trigger,
            trigger=DetectorTrigger.EXTERNAL_EDGE,
            deadtime=0.0001,
        ),
        group=group,
    )


def fastcs_eiger_arm(
    device_composite: DiffractionEssentialDevices[Any, EigerDetector],
    detector_params: DetectorParams,
    group: str,
) -> MsgGenerator:
    yield from bps.kickoff(device_composite.detector, group=group)


def fastcs_eiger_disarm(
    device_composite: DiffractionEssentialDevices[Any, EigerDetector],
) -> MsgGenerator:
    yield from bps.complete(device_composite.detector, wait=True)


def fastcs_eiger_zocalo_hw_read_signals(eiger: EigerDetector) -> Sequence[Readable]:
    # TODO update for FastCS Odin https://github.com/DiamondLightSource/mx-bluesky/issues/1076
    # return [eiger.odin.id]
    return []


def fastcs_eiger_zocalo_hw_read_mapper(doc: Event) -> ZocaloHWReadPayload:
    # TODO implement for FastCS Eiger https://github.com/DiamondLightSource/mx-bluesky/issues/1076
    ...


def fastcs_eiger_hw_read_during_signals(eiger: EigerDetector) -> Sequence[Readable]:
    return [eiger.detector.bit_depth_image]


def fastcs_eiger_hw_read_during_mapper(doc: Event) -> HWReadDuringPayload:
    # TODO implement properly for FastCS Eiger https://github.com/DiamondLightSource/mx-bluesky/issues/1076
    return HWReadDuringPayload(
        bit_depth=doc["data"]["eiger-detector-bit_depth_image"],
        ispyb_detector_id=0,  # TODO implement me
        roi_mode=False,  # TODO implement me
    )


def fastcs_eiger_tidy(
    device_composite: DiffractionEssentialDevices[Any, EigerDetector],
) -> MsgGenerator:
    # TODO disable dev_shm for fastcs odin https://github.com/DiamondLightSource/mx-bluesky/issues/1076
    yield from bps.null()
