import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.devices.aithre_lasershaping.goniometer import Goniometer


def change_goniometer_turn_speed(
    goniometer: Goniometer, velocity: float
) -> MsgGenerator:
    """Set the velocity of the goniometer"""
    yield from bps.mv(goniometer.omega.velocity, velocity)


def rotate_goniometer_relative(goniometer: Goniometer, value: float) -> MsgGenerator:
    """Adjust the goniometer position incrementally"""
    yield from bps.mvr(goniometer.omega, value)


def go_to_furthest_maximum(goniometer: Goniometer) -> MsgGenerator:
    """Go to +/-3600, whichever is further away"""
    current_value: float = yield from bps.rd(goniometer.omega)

    yield from bps.mv(goniometer.omega, -3600 if current_value > 0 else 3600)


def rotate_continuously(goniometer: Goniometer) -> MsgGenerator:
    """Oscillate the goniometer from +3600 to -3600 repeatedly"""
    yield from bps.repeat(lambda: go_to_furthest_maximum(goniometer))


def stop_goniometer(goniometer: Goniometer) -> MsgGenerator:
    """Stop the goniometer"""
    yield from bps.stop(goniometer.omega)
