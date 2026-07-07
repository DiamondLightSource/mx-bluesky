from unittest.mock import MagicMock, patch

import pytest
from dodal.devices.detector.det_dim_constants import EIGER_TYPE_EIGER2_X_16M
from pydantic import ValidationError

from mx_bluesky.common.parameters.components import (
    DiffractionExperiment,
)
from mx_bluesky.common.parameters.constants import DetectorParamConstants
from mx_bluesky.common.parameters.gridscan import (
    GridScanParams,
    GridScanParams3D,
    SpecifiedGrids,
    create_detector_params,
)


class GridParamsTest(SpecifiedGrids):
    def fast_gridscan_params(self): ...  # type: ignore


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
    "y_starts_um, z_starts_um, omega_starts_deg, y_step_sizes_um, y_steps, should_raise",
    [
        ([1, 1, 1], [1, 1, 1], [1, 1, 1], [1, 1, 1], [1, 1, 1], True),
        ([1, 1], [1, 1], [1, 1], [1, 1, 1], [1, 1], True),
        ([1, 1], [1, 1], [1, 1, 1], [1, 1], [1, 1], True),
        ([1, 1], [1, 1], [1, 1], [1, 1], [1, 1], False),
    ],
)
def test_grid_scan_params_3d_validation(
    y_starts_um: list[float],
    z_starts_um: list[float],
    omega_starts_deg: list[int],
    y_step_sizes_um: list[float],
    y_steps: list[int],
    should_raise: bool,
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

    if should_raise:
        with pytest.raises(ValidationError, match="must be length 2 for 3D scans"):
            make_params()
    else:
        make_params()


def test_create_detector_params_populates_from_diffraction_expt(
    minimal_diffraction_expt_with_sample: DiffractionExperiment,
):
    detector_params = create_detector_params(minimal_diffraction_expt_with_sample)
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
    assert not detector_params.use_roi_mode
    assert (
        detector_params.det_dist_to_beam_converter_path
        == DetectorParamConstants.BEAM_XY_LUT_PATH
    )
    assert (
        detector_params.trigger_mode
        == minimal_diffraction_expt_with_sample.trigger_mode
    )
    assert detector_params.run_number == 0


@patch("mx_bluesky.common.parameters.gridscan.get_run_number")
def test_create_detector_params_computes_run_number_if_unspecified(
    mock_get_run_number: MagicMock,
    minimal_diffraction_expt_with_sample: DiffractionExperiment,
):
    mock_get_run_number.return_value = 24680
    minimal_diffraction_expt_with_sample.run_number = None
    detector_params = create_detector_params(minimal_diffraction_expt_with_sample)
    mock_get_run_number.assert_called_once_with(
        minimal_diffraction_expt_with_sample.storage_directory,
        minimal_diffraction_expt_with_sample.file_name,
    )
    assert detector_params.run_number == 24680


@patch("mx_bluesky.common.parameters.gridscan.get_run_number")
def test_create_detector_params_uses_run_number_if_specified(
    mock_get_run_number: MagicMock,
    minimal_diffraction_expt_with_sample: DiffractionExperiment,
):
    minimal_diffraction_expt_with_sample.run_number = 13579
    detector_params = create_detector_params(minimal_diffraction_expt_with_sample)
    mock_get_run_number.assert_not_called()
    assert detector_params.run_number == 13579
