from pathlib import Path

import numpy as np
import pytest

from mx_bluesky.common.parameters.rotation import SingleRotationScan

from ...conftest import raw_params_from_file


@pytest.mark.parametrize(
    "omega_start_deg, rotation_direction, rotation_increment_deg, scan_width_deg, expected_omegas",
    [
        [0, "Positive", 0.25, 0.5, [0.0, 0.25]],
        [0, "Negative", 0.25, 0.5, [0.0, -0.25]],
    ],
)
def test_single_rotation_scan_scan_points(
    omega_start_deg: float,
    rotation_direction: str,
    rotation_increment_deg: float,
    scan_width_deg: float,
    expected_omegas: list[float],
    tmp_path: Path,
):
    params = raw_params_from_file(
        "tests/test_data/parameter_json_files/good_test_rotation_scan_parameters.json",
        tmp_path,
    )
    params |= {
        "omega_start_deg": omega_start_deg,
        "rotation_direction": rotation_direction,
        "rotation_increment_deg": rotation_increment_deg,
        "scan_width_deg": scan_width_deg,
    }
    rotation_scan = SingleRotationScan(**params)
    assert np.all(rotation_scan.scan_points["omega"] == np.array(expected_omegas))
