from dodal.common.beamlines.beamline_utils import device_factory
from dodal.devices.baton import Baton
from dodal.utils import BeamlinePrefix, get_beamline_name

BL = get_beamline_name("t01")
PREFIX = BeamlinePrefix(BL)


@device_factory()
def baton() -> Baton:
    """Get the i03 baton device, instantiate it if it hasn't already been.
    If this is called when already instantiated in i03, it will return the existing object.
    """
    return Baton(f"{PREFIX.beamline_prefix}-CS-BATON-01:")
