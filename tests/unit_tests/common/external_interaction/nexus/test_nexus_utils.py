import numpy as np
import pytest
from numpy.typing import DTypeLike
from scanspec.core import AxesPoints

from mx_bluesky.common.external_interaction.nexus.nexus_utils import (
    AxisDirection,
    create_goniometer_axes,
    vds_type_based_on_bit_depth,
)


@pytest.mark.parametrize(
    "bit_depth,expected_type",
    [(8, np.uint8), (16, np.uint16), (32, np.uint32), (100, np.uint16)],
)
def test_vds_type_is_expected_based_on_bit_depth(
    bit_depth: int, expected_type: DTypeLike
):
    assert vds_type_based_on_bit_depth(bit_depth) == expected_type


@pytest.fixture
def scan_points(test_rotation_params) -> AxesPoints:
    return next(test_rotation_params.single_rotation_scans).scan_points


@pytest.mark.parametrize(
    "omega_axis_direction, expected_axis_direction",
    [[AxisDirection.NEGATIVE, -1], [AxisDirection.POSITIVE, 1]],
)
def test_omega_axis_direction_determined_from_features(
    omega_axis_direction: AxisDirection,
    expected_axis_direction: float,
    scan_points: AxesPoints,
):
    omega_start = 0
    gonio = create_goniometer_axes(
        omega_start, scan_points, (0, 0, 0), 0, 0, omega_axis_direction
    )
    assert gonio.axes_list[0].name == "omega" and gonio.axes_list[0].vector == (
        expected_axis_direction,
        0,
        0,
    )
