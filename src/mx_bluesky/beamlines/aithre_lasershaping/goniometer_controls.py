import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.common import inject
from dodal.devices.aithre_lasershaping.goniometer import AithreGoniometer


def rotate_goniometer_relative(
    value: float, goniometer: AithreGoniometer = inject("goniometer")
) -> MsgGenerator:
    """Adjust the goniometer position incrementally"""
    yield from bps.rel_set(goniometer.omega, value, wait=True)


def change_goniometer_turn_speed(
    velocity: float, goniometer: AithreGoniometer = inject("goniometer")
) -> MsgGenerator:
    """Set the velocity of the goniometer"""
    yield from bps.mv(goniometer.omega.velocity, velocity)
