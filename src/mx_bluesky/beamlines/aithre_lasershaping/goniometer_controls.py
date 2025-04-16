import math
from enum import StrEnum

import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.common import inject
from dodal.devices.aithre_lasershaping.goniometer import Goniometer


class JogDirection(StrEnum):
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"
    ZPLUS = "z_plus"
    ZMINUS = "z_minus"


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
    direction: JogDirection,
    increment_size: float,
    goniometer: Goniometer = inject("goniometer"),
) -> MsgGenerator:
    """Adjust the goniometer stage positions vertically"""
    direction_map = {
        JogDirection.RIGHT: (goniometer.x, 1),
        JogDirection.LEFT: (goniometer.x, -1),
        JogDirection.ZPLUS: (goniometer.z, 1),
        JogDirection.ZMINUS: (goniometer.z, -1),
    }

    if direction in direction_map:
        axis, sign = direction_map[direction]
        yield from bps.mvr(axis, sign * increment_size)
    elif direction in {JogDirection.UP, JogDirection.DOWN}:
        omega: float = yield from bps.rd(goniometer.omega)
        z_component = (math.cos(math.radians(omega))) * increment_size
        y_component = (math.sin(math.radians(omega))) * increment_size
        sign = 1 if direction == JogDirection.UP else -1

        yield from bps.mvr(
            goniometer.sampz,
            sign * z_component,
            goniometer.sampy,
            sign * y_component,
        )
