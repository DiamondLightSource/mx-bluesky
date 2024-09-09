from __future__ import annotations

import bluesky.plan_stubs as bps
from dodal.devices.i24.i24_vgonio import VGonio

from mx_bluesky.beamlines.i24.jungfrau_commissioning.utils.jf_commissioning_devices import (
    ReadOnlyEnergyAndAttenuator,
    SetAttenuator,
)
from mx_bluesky.beamlines.i24.jungfrau_commissioning.utils.log import LOGGER


def rd_x_y_z(vgonio: VGonio):
    """Returns a tuple of current (x, y, z) read from EPICS"""
    x = yield from bps.rd(vgonio.x)
    y = yield from bps.rd(vgonio.yh)
    z = yield from bps.rd(vgonio.z)
    LOGGER.info(f"Read current x, yh, z: {(x, y, z)}")
    return (x, y, z)


def read_x_y_z(vgonio: VGonio):
    yield from bps.create(name="gonio xyz")  # gives name to event *descriptor* document
    yield from bps.read(vgonio.x)
    yield from bps.read(vgonio.yh)
    yield from bps.read(vgonio.z)
    yield from bps.save()


def rd_beam_parameters(ro_energ_atten: ReadOnlyEnergyAndAttenuator):
    """Returns a tuple of (transmission, wavelength, energy, intensity),
    read from EPICS"""
    transmission = yield from bps.rd(ro_energ_atten.transmission)
    wavelength = yield from bps.rd(ro_energ_atten.wavelength)
    energy = yield from bps.rd(ro_energ_atten.energy)
    intensity = yield from bps.rd(ro_energ_atten.intensity)
    flux_xbpm2 = yield from bps.rd(ro_energ_atten.flux_xbpm2)
    flux_xbpm3 = yield from bps.rd(ro_energ_atten.flux_xbpm3)
    LOGGER.info(
        f"Read current {transmission=}, {wavelength=}, {energy=}, {intensity=}, {flux_xbpm2=}, {flux_xbpm3=}"  # noqa
    )
    return (transmission, wavelength, energy, intensity, flux_xbpm2, flux_xbpm3)


def read_beam_parameters(ro_energ_atten: ReadOnlyEnergyAndAttenuator):
    """Returns a tuple of (transmission, wavelength, energy, intensity),
    read from EPICS"""

    yield from bps.create(
        name="beam params"
    )  # gives name to event *descriptor* document
    yield from bps.read(ro_energ_atten.transmission)
    yield from bps.read(ro_energ_atten.wavelength)
    yield from bps.read(ro_energ_atten.energy)
    yield from bps.read(ro_energ_atten.intensity)
    yield from bps.read(ro_energ_atten.flux_xbpm2)
    yield from bps.read(ro_energ_atten.flux_xbpm3)
    yield from bps.save()


def set_transmission(set_attenuator: SetAttenuator, transmission_fraction: float):
    LOGGER.info(f"Setting transmission to {transmission_fraction:.3f}")
    yield from bps.abs_set(
        set_attenuator.transmission_setpoint, transmission_fraction, wait=True
    )
    f1_inpos = yield from bps.rd(set_attenuator.filter_1_moving)
    f2_inpos = yield from bps.rd(set_attenuator.filter_2_moving)
    while not (f1_inpos and f2_inpos):
        LOGGER.info(f"Waiting for filters: {f1_inpos=}, {f2_inpos=}...")
        f1_inpos = yield from bps.rd(set_attenuator.filter_1_moving)
        f2_inpos = yield from bps.rd(set_attenuator.filter_2_moving)
        yield from bps.sleep(0.5)
