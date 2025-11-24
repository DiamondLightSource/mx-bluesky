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
    "direction, expected_pmac_string",
    [
        ("up", "&2#6J:-31750"),
        ("left", "&2#5J:-31750"),
        ("right", "&2#5J:31750"),
        ("down", "&2#6J:31750"),
    ],
)
def test_move_block_on_arrow_click(direction, expected_pmac_string, pmac, run_engine):
    with patch(
        "mx_bluesky.beamlines.i24.serial.web_gui_plans.oav_plans.bps.abs_set",
    ) as mock_abs_set:
        run_engine(move_block_on_arrow_click(Direction(direction), pmac))
        mock_abs_set.assert_any_call(pmac.pmac_string, expected_pmac_string, wait=True)


@pytest.mark.parametrize(
    "direction, move_size, expected_pmac_string",
    [
        ("up", "small", "&2#6J:-1250"),
        ("up", "big", "&2#6J:-3750"),
        ("left", "small", "&2#5J:-1250"),
        ("left", "big", "&2#5J:-3750"),
        ("right", "small", "&2#5J:1250"),
        ("right", "big", "&2#5J:3750"),
        ("down", "small", "&2#6J:1250"),
        ("down", "big", "&2#6J:3750"),
    ],
)
def test_move_window_on_arrow_click(
    direction, move_size, expected_pmac_string, pmac, run_engine
):
    with patch(
        "mx_bluesky.beamlines.i24.serial.web_gui_plans.oav_plans.bps.abs_set",
    ) as mock_abs_set:
        run_engine(
            move_window_on_arrow_click(Direction(direction), MoveSize(move_size), pmac)
        )
        mock_abs_set.assert_any_call(pmac.pmac_string, expected_pmac_string, wait=True)


@pytest.mark.parametrize(
    "direction, move_size, expected_pmac_string",
    [
        ("up", "small", "&2#6J:-10"),
        ("up", "big", "&2#6J:-60"),
        ("left", "small", "&2#5J:-10"),
        ("left", "big", "&2#5J:-60"),
        ("right", "small", "&2#5J:10"),
        ("right", "big", "&2#5J:60"),
        ("down", "small", "&2#6J:10"),
        ("down", "big", "&2#6J:60"),
    ],
)
def test_move_nudge_on_arrow_click(
    direction, move_size, expected_pmac_string, pmac, run_engine
):
    with patch(
        "mx_bluesky.beamlines.i24.serial.web_gui_plans.oav_plans.bps.abs_set",
    ) as mock_abs_set:
        run_engine(
            move_nudge_on_arrow_click(Direction(direction), MoveSize(move_size), pmac)
        )
        mock_abs_set.assert_any_call(pmac.pmac_string, expected_pmac_string, wait=True)
