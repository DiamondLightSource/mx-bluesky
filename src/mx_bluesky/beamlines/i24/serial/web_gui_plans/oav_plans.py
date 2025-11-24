from enum import Enum

import bluesky.plan_stubs as bps
from dodal.common import inject
from dodal.devices.i24.pmac import PMAC


class MoveSize(Enum):
    SMALL = "small"
    BIG = "big"


class Direction(Enum):
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"


def _move_direction(magnitude: float, direction: Direction, pmac):
    y_move = 0.0
    x_move = 0.0

    match direction:
        case Direction.UP:
            y_move = magnitude
        case Direction.DOWN:
            y_move = -magnitude
        case Direction.LEFT:
            x_move = -magnitude
        case Direction.RIGHT:
            x_move = magnitude

    yield from bps.abs_set(pmac.x, x_move, wait=True)
    yield from bps.abs_set(pmac.y, y_move, wait=True)


def move_block_on_arrow_click(direction: Direction, pmac: PMAC = inject("pmac")):
    magnitude = 3.1750
    yield from _move_direction(magnitude, direction, pmac)


def move_window_on_arrow_click(
    direction: Direction, size_of_move: MoveSize, pmac: PMAC = inject("pmac")
):
    match size_of_move:
        case MoveSize.SMALL:
            magnitude = 0.1250
        case MoveSize.BIG:
            magnitude = 0.3750

    yield from _move_direction(magnitude, direction, pmac)


def move_nudge_on_arrow_click(
    direction: Direction, size_of_move: MoveSize, pmac: PMAC = inject("pmac")
):
    match size_of_move:
        case MoveSize.SMALL:
            magnitude = 0.0010
        case MoveSize.BIG:
            magnitude = 0.0060

    yield from _move_direction(magnitude, direction, pmac)
