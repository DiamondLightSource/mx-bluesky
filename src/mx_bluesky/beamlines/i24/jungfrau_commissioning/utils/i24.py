from dodal.common.beamlines.beamline_utils import BL, device_instantiation
from dodal.common.beamlines.beamline_utils import set_beamline as set_utils_beamline
from dodal.devices.i24.i24_vgonio import VGonio
from dodal.devices.zebra import Zebra
from dodal.log import set_beamline
from dodal.utils import skip_device

from mx_bluesky.beamlines.i24.jungfrau_commissioning.utils.jf_commissioning_devices import (
    JungfrauM1,
    ReadOnlyEnergyAndAttenuator,
    SetAttenuator,
)

set_beamline(BL)
set_utils_beamline(BL)


def beam_params(
    wait_for_connection: bool = True, fake_with_ophyd_sim: bool = False
) -> ReadOnlyEnergyAndAttenuator:
    """Get the i24 backlight device, instantiate it if it hasn't already been.
    If this is called when already instantiated in i24, it will return the existing object.
    """
    return device_instantiation(
        device_factory=ReadOnlyEnergyAndAttenuator,
        name="beam_params",
        prefix="",
        wait=wait_for_connection,
        fake=fake_with_ophyd_sim,
    )


def attenuator(
    wait_for_connection: bool = True, fake_with_ophyd_sim: bool = False
) -> SetAttenuator:
    """Get the i24 backlight device, instantiate it if it hasn't already been.
    If this is called when already instantiated in i24, it will return the existing object.
    """
    return device_instantiation(
        device_factory=SetAttenuator,
        name="set_attenuator",
        prefix="",
        wait=wait_for_connection,
        fake=fake_with_ophyd_sim,
    )


@skip_device(lambda: BL == "s24")
def jungfrau(
    wait_for_connection: bool = True, fake_with_ophyd_sim: bool = False
) -> JungfrauM1:
    """Get the i24 detector motion device, instantiate it if it hasn't already been.
    If this is called when already instantiated in i24, it will return the existing object.
    """
    return device_instantiation(
        device_factory=JungfrauM1,
        name="jungfrau_m1",
        prefix="-EA-JNGFR-01:",
        wait=wait_for_connection,
        fake=fake_with_ophyd_sim,
    )


@skip_device(lambda: BL == "s24")
def vgonio(
    wait_for_connection: bool = True, fake_with_ophyd_sim: bool = False
) -> VGonio:
    """Get the i24 vgonio device, instantiate it if it hasn't already been.
    If this is called when already instantiated, it will return the existing object.
    """
    return device_instantiation(
        VGonio,
        "vgonio",
        "-MO-VGON-01:",
        wait_for_connection,
        fake_with_ophyd_sim,
    )


def zebra(wait_for_connection: bool = True, fake_with_ophyd_sim: bool = False) -> Zebra:
    """Get the i24 zebra device, instantiate it if it hasn't already been.
    If this is called when already instantiated in i24, it will return the existing object.
    """
    return device_instantiation(
        Zebra,
        "zebra",
        "-EA-ZEBRA-01:",
        wait_for_connection,
        fake_with_ophyd_sim,
    )
