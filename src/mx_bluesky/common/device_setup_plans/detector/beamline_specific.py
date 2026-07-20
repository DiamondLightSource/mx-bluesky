from __future__ import annotations

import dataclasses
from collections.abc import Callable, Sequence
from typing import Generic, TypeVar

from bluesky.utils import MsgGenerator
from dodal.devices.detector import DetectorParams

from mx_bluesky.common.parameters.device_composites import DiffractionEssentialDevices

TDiffractionEssentialDevices = TypeVar(
    "TDiffractionEssentialDevices", bound=DiffractionEssentialDevices
)


@dataclasses.dataclass
class BeamlineSpecificDetectorFeatures(Generic[TDiffractionEssentialDevices]):
    """Defines plans specific to arming and disarming the detector.
    Attributes:
        pre_arm_detector_plan: A plan that may be called early on to start arming the detector.
            Supplied with a group name that will be waited on to ensure pre-arming completes.
        arm_detector_plan: A plan that is called later to fully arm the detector. Supplied with a group name
            that will be waited on to ensure arming completes.
        disarm_detector_plan: A plan that will be called to complete the acquisition.
        tidy_detector_plan: The detector-specific plan for cleaning up the detector.
        detector_zocalo_hw_read_signals: The list of signals to read when generating the ZOCALO_HW_READ event.
        detector_hw_read_during_signals: The list of signals to read when generating the HARDWARE_READ_DURING event.
    """

    pre_arm_detector_plan: Callable[
        [TDiffractionEssentialDevices, DetectorParams, str], MsgGenerator
    ]
    arm_detector_plan: Callable[
        [TDiffractionEssentialDevices, DetectorParams, str], MsgGenerator
    ]
    disarm_detector_plan: Callable[[TDiffractionEssentialDevices], MsgGenerator]
    tidy_detector_plan: Callable[[TDiffractionEssentialDevices], MsgGenerator]
    detector_zocalo_hw_read_signals: Sequence
    detector_hw_read_during_signals: Sequence
