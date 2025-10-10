import bluesky.plan_stubs as bps

from mx_bluesky.beamlines.i24.jungfrau_commissioning.composites import (
    RotationScanComposite,
)
from mx_bluesky.beamlines.i24.parameters.constants import PlanNameConstants
from mx_bluesky.common.utils.log import LOGGER


def read_devices_for_metadata(composite: RotationScanComposite):
    yield from bps.create(PlanNameConstants.ROTATION_META_READ)
    yield from bps.read(composite.dcm.energy_in_kev)
    yield from bps.read(composite.dcm.wavelength_in_a)
    val = yield from bps.read(composite.det_stage.z)
    LOGGER.info(f"DURING META READ: read value {val} as det distance")
    yield from bps.save()
