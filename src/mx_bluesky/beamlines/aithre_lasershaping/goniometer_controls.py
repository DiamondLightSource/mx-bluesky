import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.common import inject
from dodal.devices.aithre_lasershaping.goniometer import Goniometer


def rotate_goniometer_relative(
    value: float, goniometer: Goniometer = inject("goniometer")
) -> MsgGenerator:
    """Adjust the goniometer position incrementally"""
    yield from bps.rel_set(goniometer.omega, value, wait=True)


def change_goniometer_turn_speed(
    velocity: float, goniometer: Goniometer = inject("goniometer")
) -> MsgGenerator:
    """Set the velocity of the goniometer"""
    yield from bps.mv(goniometer.omega.velocity, velocity)


def go_to_furthest_maximum(
    goniometer: Goniometer = inject("goniometer"),
) -> MsgGenerator:
    """Go to +/-3600, whichever is further away"""
    current_value: float = yield from bps.rd(goniometer.omega.user_readback)

    yield from bps.mv(goniometer.omega, -3600 if current_value > 0 else 3600)
