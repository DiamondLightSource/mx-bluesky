from pathlib import Path

import numpy as np
import pytest

from mx_bluesky.common.parameters.components import get_param_version
from mx_bluesky.common.parameters.constants import USE_NUMTRACKER
from mx_bluesky.common.parameters.rotation import SingleRotationScan, images_in_sweep

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


@pytest.mark.parametrize(
    "scan_width_deg, rotation_increment_deg, expected",
    [
        (360, 0.1, 3600),
        (90, 0.2, 450),
        (0.1, 0.1, 1),
        (360, 0.05, 7200),
    ],
)
def test_a_sweep_that_divides_exactly_gives_the_whole_number_of_images(
    scan_width_deg: float, rotation_increment_deg: float, expected: int
):
    assert images_in_sweep(scan_width_deg, rotation_increment_deg) == expected


@pytest.mark.parametrize(
    "scan_width_deg, rotation_increment_deg, expected",
    [
        # Each of these divides exactly in decimal but lands just under a whole number in
        # floating point, so truncating the quotient would collect one image too few.
        (2.15, 0.05, 43),
        (4.05, 0.05, 81),
        (8.1, 0.05, 162),
    ],
)
def test_floating_point_error_does_not_cost_an_image(
    scan_width_deg: float, rotation_increment_deg: float, expected: int
):
    assert images_in_sweep(scan_width_deg, rotation_increment_deg) == expected


@pytest.mark.parametrize(
    "scan_width_deg, rotation_increment_deg, expected",
    [
        (10, 0.3, 33),
        (1, 0.7, 1),
        (0.5, 0.3, 1),
    ],
)
def test_a_sweep_that_does_not_divide_exactly_rounds_down(
    scan_width_deg: float, rotation_increment_deg: float, expected: int
):
    # A partial image at the end is not collected, so the tolerance must not round up.
    assert images_in_sweep(scan_width_deg, rotation_increment_deg) == expected


def test_detector_params_under_numtracker_raises_rather_than_making_a_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # DetectorParams needs a directory that exists, so detector_params makes one - but
    # storage_directory is a placeholder rather than a path until numtracker fills it
    # in, and making that left a directory called "from numtracker" in the cwd.
    monkeypatch.chdir(tmp_path)
    params = SingleRotationScan(
        sample_id=1,
        visit=USE_NUMTRACKER,
        parameter_model_version=get_param_version(),
        file_name="rotations",
        exposure_time_s=0.01,
        storage_directory=USE_NUMTRACKER,
        detector_distance_mm=200,
    )

    with pytest.raises(ValueError, match="until numtracker"):
        _ = params.detector_params

    assert list(tmp_path.iterdir()) == []
