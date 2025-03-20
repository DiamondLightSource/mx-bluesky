import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.devices.aithre_lasershaping.goniometer import Goniometer

DEFAULT_VELOCITIES = [5.0, 10.0, 20.0, 40.0, 80.0, 90.0]
DEFAULT_POSITIONS = [
    300.0,
    -300.0,
    600.0,
    -600.0,
    1200.0,
    -1200.0,
    2400.0,
    -2400.0,
    3600.0,
    -3600.0,
]


def check_omega_performance(
    goniometer: Goniometer,
    velocities: list[float] = DEFAULT_VELOCITIES,
    values: list[float] = DEFAULT_POSITIONS,
) -> MsgGenerator:
    """Move the goniometer from positive to negative to check omega performance"""
    for omega_velocity in velocities:
        yield from bps.abs_set(goniometer.omega.velocity, omega_velocity, wait=True)
        for omega_value in values:
            yield from bps.abs_set(goniometer.omega, omega_value, wait=True)
