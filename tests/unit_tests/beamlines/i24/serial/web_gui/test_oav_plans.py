from unittest.mock import patch

import pytest

from mx_bluesky.beamlines.i24.serial.web_gui_plans.oav_plans import (
    move_block_on_arrow_click,
)


@pytest.mark.parametrize(
    "direction, expected_pmac_string",
    [
        ("up", "&2#6J:-31750"),
        ("right", "&2#5J:31750"),
    ],
)
def test_move_block_on_arrow_click(direction, expected_pmac_string, pmac):
    with patch(
        "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_moveonclick.bps.abs_set",
    ) as mock_abs_set:
        plan = move_block_on_arrow_click(direction, pmac)
        list(plan)
        mock_abs_set.assert_called_with(pmac, expected_pmac_string, wait=True)
