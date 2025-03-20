import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.devices.aithre_lasershaping.goniometer import Goniometer


def check_omega_performance(goniometer: Goniometer) -> MsgGenerator:
    for omega_velocity in [5, 10, 20, 40, 80, 90]:
        yield from bps.abs_set(goniometer.omega.velocity, omega_velocity, wait=True)
        for omega_value in [
            300,
            -300,
            600,
            -600,
            1200,
            -1200,
            2400,
            -2400,
            3600,
            -3600,
        ]:
            yield from bps.abs_set(goniometer.omega, omega_value, wait=True)
