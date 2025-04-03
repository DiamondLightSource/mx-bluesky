import math

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


def jog_sample(
    direction: str, increment_size: float, goniometer: Goniometer = inject("goniometer")
) -> MsgGenerator:
    """Adjust the goniometer stage positions vertically"""
    direction_map = {
        "right": (goniometer.x, 1),
        "left": (goniometer.x, -1),
        "z_plus": (goniometer.z, 1),
        "z_minus": (goniometer.z, -1),
    }

    if direction in direction_map:
        axis, sign = direction_map[direction]
        yield from bps.mvr(axis, sign * increment_size)
    elif direction in {"up", "down"}:
        omega: float = yield from bps.rd(goniometer.omega)
        x_component = (math.cos(math.radians(omega))) * increment_size
        y_component = (math.sin(math.radians(omega))) * increment_size
        sign = 1 if direction == "up" else -1

        yield from bps.rel_set(goniometer.x, sign * x_component, group="gonio_stage")
        yield from bps.rel_set(goniometer.y, sign * y_component, group="gonio_stage")
        yield from bps.wait("gonio_stage")
