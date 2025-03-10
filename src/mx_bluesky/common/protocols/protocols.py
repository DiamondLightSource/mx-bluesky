from typing import Protocol, runtime_checkable

from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
from dodal.devices.xbpm_feedback import XBPMFeedback


@runtime_checkable
class XBPMPauseDevices(Protocol):
    xbpm_feedback: XBPMFeedback
    attenuator: BinaryFilterAttenuator
