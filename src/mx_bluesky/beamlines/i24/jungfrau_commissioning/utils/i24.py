from dodal.common.beamlines.beamline_utils import BL, device_instantiation
from dodal.common.beamlines.beamline_utils import set_beamline as set_utils_beamline
from dodal.devices.backlight import Backlight
from dodal.devices.detector import DetectorParams
from dodal.devices.eiger import EigerDetector
from dodal.devices.i24.i24_detector_motion import DetectorMotion
from dodal.devices.i24.i24_vgonio import VGonio
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.zebra import Zebra
from dodal.log import set_beamline
from dodal.utils import get_beamline_name, skip_device

from mx_bluesky.beamlines.i24.jungfrau_commissioning.utils.jf_commissioning_devices import (
    JungfrauM1,
    ReadOnlyEnergyAndAttenuator,
    SetAttenuator,
)

BL = get_beamline_name("s24")
set_beamline(BL)
set_utils_beamline(BL)


def backlight(
    wait_for_connection: bool = True, fake_with_ophyd_sim: bool = False
) -> Backlight:
    """Get the i24 backlight device, instantiate it if it hasn't already been.
    If this is called when already instantiated in i24, it will return the existing object.
    """
    return device_instantiation(
        device=Backlight,
        name="backlight",
        prefix="-MO-BL-01:",
        wait=wait_for_connection,
        fake=fake_with_ophyd_sim,
    )


def beam_params(
    wait_for_connection: bool = True, fake_with_ophyd_sim: bool = False
) -> ReadOnlyEnergyAndAttenuator:
    """Get the i24 backlight device, instantiate it if it hasn't already been.
    If this is called when already instantiated in i24, it will return the existing object.
    """
    return device_instantiation(
        device=ReadOnlyEnergyAndAttenuator,
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
        device=SetAttenuator,
        name="set_attenuator",
        prefix="",
        wait=wait_for_connection,
        fake=fake_with_ophyd_sim,
    )


@skip_device(lambda: BL == "s24")
def detector_motion(
    wait_for_connection: bool = True, fake_with_ophyd_sim: bool = False
) -> DetectorMotion:
    """Get the i24 detector motion device, instantiate it if it hasn't already been.
    If this is called when already instantiated in i24, it will return the existing object.
    """
    return device_instantiation(
        device=DetectorMotion,
        name="detector_motion",
        prefix="-MO-DET-01:",
        wait=wait_for_connection,
        fake=fake_with_ophyd_sim,
    )


@skip_device(lambda: BL == "s24")
def eiger(
    wait_for_connection: bool = True,
    fake_with_ophyd_sim: bool = False,
    params: DetectorParams | None = None,
) -> EigerDetector:
    """Get the i24 Eiger device, instantiate it if it hasn't already been.
    If this is called when already instantiated, it will return the existing object.
    If called with params, will update those params to the Eiger object.
    """

    def set_params(eiger: EigerDetector):
        if params is not None:
            eiger.set_detector_parameters(params)

    return device_instantiation(
        device=EigerDetector,
        name="eiger",
        prefix="-EA-EIGER-01:",
        wait=wait_for_connection,
        fake=fake_with_ophyd_sim,
        post_create=set_params,
    )


@skip_device(lambda: BL == "s24")
def jungfrau(
    wait_for_connection: bool = True, fake_with_ophyd_sim: bool = False
) -> JungfrauM1:
    """Get the i24 detector motion device, instantiate it if it hasn't already been.
    If this is called when already instantiated in i24, it will return the existing object.
    """
    return device_instantiation(
        device=JungfrauM1,
        name="jungfrau_m1",
        prefix="-EA-JNGFR-01:",
        wait=wait_for_connection,
        fake=fake_with_ophyd_sim,
    )


@skip_device(lambda: BL == "s24")
def oav(wait_for_connection: bool = True, fake_with_ophyd_sim: bool = False) -> OAV:
    """Get the i24 OAV device, instantiate it if it hasn't already been.
    If this is called when already instantiated in i24, it will return the existing object.
    """
    return device_instantiation(
        OAV,
        "oav",
        "",
        wait_for_connection,
        fake_with_ophyd_sim,
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
