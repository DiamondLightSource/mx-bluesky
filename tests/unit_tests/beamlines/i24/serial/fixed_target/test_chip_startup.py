from unittest.mock import patch

import pytest

from mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_StartUp_py3v1 import (
    check_files,
    fiducials,
    pathli,
)


def test_fiducials():
    assert fiducials(0) == []
    assert fiducials(1) == []
    assert fiducials(2) is None


@patch("mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_StartUp_py3v1.os")
@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_StartUp_py3v1.read_parameter_file"
)
def test_check_files(fake_read_params, mock_os, dummy_params_without_pp):
    fake_read_params.return_value = dummy_params_without_pp
    check_files("i24", [".a", ".b"])


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
