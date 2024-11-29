from dodal.common.beamlines.beamline_utils import device_instantiation, set_beamline
from dodal.devices.i24.vgonio import VerticalGoniometer

set_beamline("s24")


def vgonio(
    wait_for_connection: bool = True, fake_with_ophyd_sim: bool = True
) -> VerticalGoniometer:
    """Get the i24 vertical goniometer device, instantiate it if it hasn't already been.
    If this is called when already instantiated, it will return the existing object.
    """
    return device_instantiation(
        VerticalGoniometer,
        "vgonio",
        "-MO-VGON-01:",
        wait_for_connection,
        fake_with_ophyd_sim,
    )
