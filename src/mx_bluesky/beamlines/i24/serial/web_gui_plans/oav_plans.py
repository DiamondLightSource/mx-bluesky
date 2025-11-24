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


def _move_direction(magnitude: int, direction: Direction, pmac):
    y_move = "&2#6J:0"
    x_move = "&2#5J:0"

    match direction:
        case Direction.UP:
            y_move = f"&2#6J:{-magnitude}"
        case Direction.DOWN:
            y_move = f"&2#6J:{magnitude}"
        case Direction.LEFT:
            x_move = f"&2#5J:{-magnitude}"
        case Direction.RIGHT:
            x_move = f"&2#5J:{magnitude}"

    yield from bps.abs_set(pmac.pmac_string, x_move, wait=True)
    yield from bps.abs_set(pmac.pmac_string, y_move, wait=True)


def move_block_on_arrow_click(direction: Direction, pmac: PMAC = inject("pmac")):
    magnitude = 31750
    yield from _move_direction(magnitude, direction, pmac)


def move_window_on_arrow_click(
    direction: Direction, size_of_move: MoveSize, pmac: PMAC = inject("pmac")
):
    match size_of_move:
        case MoveSize.SMALL:
            magnitude = 1250
        case MoveSize.BIG:
            magnitude = 3750

    yield from _move_direction(magnitude, direction, pmac)


def move_nudge_on_arrow_click(
    direction: Direction, size_of_move: MoveSize, pmac: PMAC = inject("pmac")
):
    match size_of_move:
        case MoveSize.SMALL:
            magnitude = 10
        case MoveSize.BIG:
            magnitude = 60

    yield from _move_direction(magnitude, direction, pmac)
