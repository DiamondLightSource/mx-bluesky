import json
from math import isclose
from unittest.mock import MagicMock, patch

import pytest
from dodal.devices.detector.det_dim_constants import EIGER_TYPE_EIGER2_X_16M
from dodal.devices.eiger import FREE_RUN_MAX_IMAGES
from pydantic import ValidationError

from mx_bluesky.common.parameters.components import (
    DiffractionExperiment,
)
from mx_bluesky.common.parameters.constants import DetectorParamConstants
from mx_bluesky.common.parameters.gridscan import (
    GridScanParams,
    GridScanParams3D,
    create_detector_params_for_grid_scan,
)


@pytest.mark.parametrize(
    "y_starts_um, z_starts_um, omega_starts_deg, y_step_sizes_um, y_steps, should_raise",
    [
        ([1, 1], [1], [1], [1], [1, 1], True),
        (
            [
                1,
            ],
            [1],
            [1],
            [1, 1, 2, 3],
            [1],
            True,
        ),
        ([1, 1], [1, 1], [1, 1], [1, 1], [1], True),
        ([1, 1, 1, 1], [1, 1, 1], [1], [1], [1, 1], True),
        ([1, 1, 1], [1, 1, 1], [1, 1, 1], [1, 1, 1], [1, 1, 1], False),
    ],
)
def test_grid_scan_params_validation(
    y_starts_um: list[float],
    z_starts_um: list[float],
    omega_starts_deg: list[int],
    y_step_sizes_um: list[float],
    y_steps: list[int],
    should_raise: bool,
):
    def make_params():
        GridScanParams(
            x_start_um=0,
            y_starts_um=y_starts_um,
            z_starts_um=z_starts_um,
            omega_starts_deg=omega_starts_deg,
            y_step_sizes_um=y_step_sizes_um,
            y_steps=y_steps,
            x_steps=5,
        )

    if should_raise:
        with pytest.raises(
            ValidationError, match="Fields must all have the same length:"
        ):
            make_params()
    else:
        make_params()


@pytest.mark.parametrize(
    "y_starts_um, z_starts_um, omega_starts_deg, y_step_sizes_um, y_steps, match",
    [
        (
            [1, 1, 1],
            [1, 1, 1],
            [1, 1, 1],
            [1, 1, 1],
            [1, 1, 1],
            "must be length 2 for 3D scans",
        ),
        (
            [1, 1],
            [1, 1],
            [1, 1],
            [1, 1, 1],
            [1, 1],
            "Fields must all have the same length:",
        ),
        (
            [1, 1],
            [1, 1],
            [1, 1, 1],
            [1, 1],
            [1, 1],
            "Fields must all have the same length:",
        ),
        ([1, 1], [1, 1], [1, 1], [1, 1], [1, 1], None),
    ],
)
def test_grid_scan_params_3d_validation(
    y_starts_um: list[float],
    z_starts_um: list[float],
    omega_starts_deg: list[int],
    y_step_sizes_um: list[float],
    y_steps: list[int],
    match: str | None,
):
    def make_params():
        GridScanParams3D(
            x_start_um=0,
            y_starts_um=y_starts_um,
            z_starts_um=z_starts_um,
            omega_starts_deg=omega_starts_deg,
            y_step_sizes_um=y_step_sizes_um,
            y_steps=y_steps,
            x_steps=5,
        )

    if match:
        with pytest.raises(ValidationError, match=match):
            make_params()
    else:
        make_params()


def test_create_detector_params_for_grid_scan_populates_from_diffraction_expt(
    minimal_diffraction_expt_with_sample: DiffractionExperiment,
):
    detector_params = create_detector_params_for_grid_scan(
        minimal_diffraction_expt_with_sample
    )
    assert (
        detector_params.detector_size_constants.det_type_string
        == EIGER_TYPE_EIGER2_X_16M
    )
    assert detector_params.expected_energy_ev == 100
    assert detector_params.exposure_time_s == 0.1
    assert (
        detector_params.directory
        == minimal_diffraction_expt_with_sample.storage_directory
    )
    assert detector_params.prefix == "file_name"
    assert detector_params.detector_distance == 100.0
    assert detector_params.omega_start == 0
    assert detector_params.omega_increment == 0
    assert detector_params.num_images_per_trigger == 1
    assert detector_params.num_triggers == FREE_RUN_MAX_IMAGES
    assert not detector_params.use_roi_mode
    assert (
        detector_params.det_dist_to_beam_converter_path
        == DetectorParamConstants.BEAM_XY_LUT_PATH
    )
    assert (
        detector_params.trigger_mode
        == minimal_diffraction_expt_with_sample.trigger_mode
    )
    assert detector_params.run_number == 1


@patch("mx_bluesky.common.parameters.gridscan.get_run_number")
def test_create_detector_params_for_grid_scan_computes_run_number_if_unspecified(
    mock_get_run_number: MagicMock,
    minimal_diffraction_expt_with_sample: DiffractionExperiment,
):
    mock_get_run_number.return_value = 24680
    minimal_diffraction_expt_with_sample.run_number = None
    detector_params = create_detector_params_for_grid_scan(
        minimal_diffraction_expt_with_sample
    )
    mock_get_run_number.assert_called_once_with(
        minimal_diffraction_expt_with_sample.storage_directory,
        minimal_diffraction_expt_with_sample.file_name,
    )
    assert detector_params.run_number == 24680


@patch("mx_bluesky.common.parameters.gridscan.get_run_number")
def test_create_detector_params_for_grid_scan_uses_run_number_if_specified(
    mock_get_run_number: MagicMock,
    minimal_diffraction_expt_with_sample: DiffractionExperiment,
):
    minimal_diffraction_expt_with_sample.run_number = 13579
    detector_params = create_detector_params_for_grid_scan(
        minimal_diffraction_expt_with_sample
    )
    mock_get_run_number.assert_not_called()
    assert detector_params.run_number == 13579


# fmt: off
expected_scan_points = [
    # Grid 1, 5x7
    {
        "sam_x": [
            0.123, 20.123, 40.123, 60.123, 80.123,
            80.123, 60.123, 40.123, 20.123, 0.123,
            0.123, 20.123, 40.123, 60.123, 80.123,
            80.123, 60.123, 40.123, 20.123, 0.123,
            0.123, 20.123, 40.123, 60.123, 80.123,
            80.123, 60.123, 40.123, 20.123, 0.123,
            0.123, 20.123, 40.123, 60.123, 80.123,
        ],
        "sam_y": [
            0.777, 0.777, 0.777, 0.777, 0.777,
            20.777, 20.777, 20.777, 20.777, 20.777,
            40.777, 40.777, 40.777, 40.777, 40.777,
            60.777, 60.777, 60.777, 60.777, 60.777,
            80.777, 80.777, 80.777, 80.777, 80.777,
            100.777, 100.777, 100.777, 100.777, 100.777,
            120.777, 120.777, 120.777, 120.777, 120.777,
        ],
        "sam_z": [
            0.05, 0.05, 0.05, 0.05, 0.05,
            0.05, 0.05, 0.05, 0.05, 0.05,
            0.05, 0.05, 0.05, 0.05, 0.05,
            0.05, 0.05, 0.05, 0.05, 0.05,
            0.05, 0.05, 0.05, 0.05, 0.05,
            0.05, 0.05, 0.05, 0.05, 0.05,
            0.05, 0.05, 0.05, 0.05, 0.05,
        ],
    },
    # Grid 2, 5x9
    {
        "sam_x": [
            0.123, 20.123, 40.123, 60.123, 80.123,
            80.123, 60.123, 40.123, 20.123, 0.123,
            0.123, 20.123, 40.123, 60.123, 80.123,
            80.123, 60.123, 40.123, 20.123, 0.123,
            0.123, 20.123, 40.123, 60.123, 80.123,
            80.123, 60.123, 40.123, 20.123, 0.123,
            0.123, 20.123, 40.123, 60.123, 80.123,
            80.123, 60.123, 40.123, 20.123, 0.123,
            0.123, 20.123, 40.123, 60.123, 80.123,
        ],
        "sam_y": [
            2, 2, 2, 2, 2,
            22, 22, 22, 22, 22,
            42, 42, 42, 42, 42,
            62, 62, 62, 62, 62,
            82, 82, 82, 82, 82,
            102, 102, 102, 102, 102,
            122, 122, 122, 122, 122,
            142, 142, 142, 142, 142,
            162, 162, 162, 162, 162,
        ],
        "sam_z": [
            2, 2, 2, 2, 2,
            2, 2, 2, 2, 2,
            2, 2, 2, 2, 2,
            2, 2, 2, 2, 2,
            2, 2, 2, 2, 2,
            2, 2, 2, 2, 2,
            2, 2, 2, 2, 2,
            2, 2, 2, 2, 2,
            2, 2, 2, 2, 2,
        ],
    },
]
# fmt: on


def test_minimal_3d_gridscan_params(minimal_gridscan_params: GridScanParams):
    scan_points = minimal_gridscan_params.scan_points
    assert all(
        {"sam_x", "sam_y", "sam_z"} == set(scan_point.keys())
        for scan_point in scan_points
    )
    assertions_and_messages = [
        (
            isclose(actual_pt, expected_pt, abs_tol=1e-6),
            f"{actual_pt:.3f} == {expected_pt}",
        )
        for actual_grid, expected_grid in zip(
            scan_points, expected_scan_points, strict=True
        )
        for axis in expected_grid.keys()
        for actual_pt, expected_pt in zip(
            actual_grid[axis], expected_grid[axis], strict=True
        )
    ]
    assert all(b for b, _ in assertions_and_messages), (
        "actual != expected: " + ", ".join(msg for _, msg in assertions_and_messages)
    )
    assert minimal_gridscan_params.num_images == (5 * 7 + 5 * 9)
    assert minimal_gridscan_params.scan_indices == [0, 35]


def test_serialise_deserialise(minimal_gridscan_params: GridScanParams):
    serialised = json.loads(minimal_gridscan_params.model_dump_json())
    deserialised = GridScanParams(**serialised)
    assert deserialised == minimal_gridscan_params
