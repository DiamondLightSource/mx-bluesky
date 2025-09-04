import bluesky.plan_stubs as bps
from dodal.devices.attenuator.attenuator import EnumFilterAttenuator

from mx_bluesky.beamlines.i24.jungfrau_commissioning.composites import (
    RotationScanComposite,
)
from mx_bluesky.common.utils.log import LOGGER

METADATA_READ = "metadata read"


# Long term this should be done by adding a set function to the attenuator device.
# See https://github.com/DiamondLightSource/dodal/issues/972
def set_transmission(
    set_attenuator: EnumFilterAttenuator, transmission_fraction: float
):
    LOGGER.info(f"Setting transmission to {transmission_fraction:.3f}")
    yield from bps.abs_set(
        set_attenuator.transmission_setpoint, transmission_fraction, wait=True
    )
    f1_inpos = yield from bps.rd(set_attenuator.filters[0])
    f2_inpos = yield from bps.rd(set_attenuator.filters[1])
    while not (f1_inpos and f2_inpos):
        LOGGER.info(f"Waiting for filters: {f1_inpos=}, {f2_inpos=}...")
        f1_inpos = yield from bps.rd(set_attenuator.filters[0])
        f2_inpos = yield from bps.rd(set_attenuator.filters[1])
        yield from bps.sleep(0.5)


def read_devices_for_metadata(composite: RotationScanComposite):
    yield from bps.create(METADATA_READ)
    yield from bps.read(composite.dcm.energy_in_kev)
    yield from bps.read(composite.dcm.wavelength_in_a)
    yield from bps.read(composite.det_stage.z)
    yield from bps.save()
