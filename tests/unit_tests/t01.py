"""
A minimal test beamline that contains only a baton, for use in tests which need a beamline
but not all the devices, so that test execution isn't slowed down by loading lots of
python modules/creating objects.
See Also:
    use_beamline_t01()
"""

from dodal.device_manager import DeviceManager
from dodal.devices.baton import Baton
from dodal.devices.detector.detector_motion import DetectorMotion
from dodal.devices.synchrotron import Synchrotron
from dodal.devices.xbpm_feedback import XBPMFeedback
from dodal.utils import BeamlinePrefix, get_beamline_name

BL = get_beamline_name("t01")
PREFIX = BeamlinePrefix(BL)

devices = DeviceManager()


@devices.factory()
def baton() -> Baton:
    return Baton(f"{PREFIX.beamline_prefix}-CS-BATON-01:")


@devices.factory()
def synchrotron() -> Synchrotron:
    return Synchrotron()


@devices.factory()
def xbpm_feedback() -> XBPMFeedback:
    return XBPMFeedback(
        PREFIX.beamline_prefix,
        "xbpm_feedback",
    )


@devices.factory()
def detector_motion() -> DetectorMotion:
    return DetectorMotion(
        device_prefix=f"{PREFIX.beamline_prefix}-MO-DET-01:",
        pmac_prefix=f"{PREFIX.beamline_prefix}-MO-PMAC-02:",
    )
