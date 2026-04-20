import pytest

from mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_StartUp_py3v1 import (
    fiducials,
    pathli,
)


def test_fiducials():
    assert fiducials(0) == []
    assert fiducials(1) == []
    assert fiducials(2) is None


@pytest.mark.parametrize(
    "list_in, way, reverse, expected_res",
    [
        (
            [1, 2, 3],
            "typewriter",
            False,
            [1, 2, 3] * 3,
        ),  # Result should be list * len(list)
        ([1, 2, 3], "typewriter", True, [3, 2, 1] * 3),  # list[::-1] * len(list)
        ([4, 5], "snake", False, [4, 5, 5, 4]),  # Snakes the list
        ([4, 5], "expand", False, [4, 4, 5, 5]),  # Repeats each value
    ],
)
def test_pathli(list_in, way, reverse, expected_res):
    assert pathli(list_in, way, reverse) == expected_res
