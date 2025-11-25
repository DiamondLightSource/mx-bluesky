from unittest.mock import patch

import pytest

from mx_bluesky.beamlines.i24.serial.web_gui_plans.oav_plans import (
    Direction,
    MoveSize,
    move_block_on_arrow_click,
    move_nudge_on_arrow_click,
    move_window_on_arrow_click,
)


@pytest.mark.parametrize(
    "direction, expected_value",
    [
        ("up", 3.1750),
        ("left", -3.1750),
        ("right", 3.1750),
        ("down", -3.1750),
    ],
)
def test_move_block_on_arrow_click(direction, expected_value, pmac, run_engine):
    with patch(
        "mx_bluesky.beamlines.i24.serial.web_gui_plans.oav_plans.bps.abs_set",
    ) as mock_abs_set:
        run_engine(move_block_on_arrow_click(Direction(direction), pmac))
        if direction in ["left", "right"]:
            mock_abs_set.assert_any_call(pmac.x, expected_value, wait=True)
        else:
            mock_abs_set.assert_any_call(pmac.y, expected_value, wait=True)


@pytest.mark.parametrize(
    "direction, move_size, expected_value",
    [
        ("up", "small", 0.1250),
        ("up", "big", 0.3750),
        ("left", "small", -0.1250),
        ("left", "big", -0.3750),
        ("right", "small", 0.1250),
        ("right", "big", 0.3750),
        ("down", "small", -0.1250),
        ("down", "big", -0.3750),
    ],
)
def test_move_window_on_arrow_click(
    direction, move_size, expected_value, pmac, run_engine
):
    with patch(
        "mx_bluesky.beamlines.i24.serial.web_gui_plans.oav_plans.bps.abs_set",
    ) as mock_abs_set:
        run_engine(
            move_window_on_arrow_click(Direction(direction), MoveSize(move_size), pmac)
        )
        if direction in ["left", "right"]:
            mock_abs_set.assert_any_call(pmac.x, expected_value, wait=True)
        else:
            mock_abs_set.assert_any_call(pmac.y, expected_value, wait=True)


@pytest.mark.parametrize(
    "direction, move_size, expected_value",
    [
        ("up", "small", 0.0010),
        ("up", "big", 0.0060),
        ("left", "small", -0.0010),
        ("left", "big", -0.0060),
        ("right", "small", 0.0010),
        ("right", "big", 0.0060),
        ("down", "small", -0.0010),
        ("down", "big", -0.0060),
    ],
)
def test_move_nudge_on_arrow_click(
    direction, move_size, expected_value, pmac, run_engine
):
    with patch(
        "mx_bluesky.beamlines.i24.serial.web_gui_plans.oav_plans.bps.abs_set",
    ) as mock_abs_set:
        run_engine(
            move_nudge_on_arrow_click(Direction(direction), MoveSize(move_size), pmac)
        )
        if direction in ["left", "right"]:
            mock_abs_set.assert_any_call(pmac.x, expected_value, wait=True)
        else:
            mock_abs_set.assert_any_call(pmac.y, expected_value, wait=True)
