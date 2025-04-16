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
    """Adjust the goniometer stage positions"""
    direction_map = {
        JogDirection.RIGHT: (goniometer.x, 1),
        JogDirection.LEFT: (goniometer.x, -1),
        JogDirection.ZPLUS: (goniometer.z, 1),
        JogDirection.ZMINUS: (goniometer.z, -1),
        JogDirection.UP: (goniometer.vertical_position, 1),
        JogDirection.DOWN: (goniometer.vertical_position, -1),
    }

    axis, sign = direction_map[direction]
    yield from bps.mvr(axis, sign * increment_size)
