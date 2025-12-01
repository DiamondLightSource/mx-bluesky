"""
A minimal test beamline that contains only a baton, for use in tests which need a beamline
but not all the devices, so that test execution isn't slowed down by loading lots of
python modules/creating objects.
See Also:
    use_beamline_t01()
"""

from dodal.device_manager import DeviceManager
from dodal.devices.baton import Baton
from dodal.devices.xbpm_feedback import XBPMFeedback
from dodal.utils import BeamlinePrefix, get_beamline_name

BL = get_beamline_name("t01")
PREFIX = BeamlinePrefix(BL)

devices = DeviceManager()


@devices.factory()
def baton() -> Baton:
    """Get the i03 baton device, instantiate it if it hasn't already been.
    If this is called when already instantiated in i03, it will return the existing object.
    """
    return Baton(f"{PREFIX.beamline_prefix}-CS-BATON-01:")


@devices.factory()
def xbpm_feedback() -> XBPMFeedback:
    """Get the i03 XBPM feeback device, instantiate it if it hasn't already been.
    If this is called when already instantiated in i03, it will return the existing object.
    """
    return XBPMFeedback(
        PREFIX.beamline_prefix,
        "xbpm_feedback",
    )
