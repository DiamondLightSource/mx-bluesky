from typing import Protocol, runtime_checkable

from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
from dodal.devices.dcm import DCM
from dodal.devices.undulator import Undulator
from dodal.devices.xbpm_feedback import XBPMFeedback


@runtime_checkable
class XBPMPauseDevices(Protocol):
    undulator: Undulator
    xbpm_feedback: XBPMFeedback
    attenuator: BinaryFilterAttenuator
    dcm: DCM
