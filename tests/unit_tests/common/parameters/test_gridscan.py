import pytest
from pydantic import ValidationError

from mx_bluesky.common.parameters.components import get_param_version
from mx_bluesky.common.parameters.gridscan import (
    SpecifiedGrids,
    SpecifiedThreeDGridScan,
)


class GridParamsTest(SpecifiedGrids):
    def fast_gridscan_params(): ...  # type: ignore


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
def test_specified_grids_validation_error(
    y_starts_um: list[float],
    z_starts_um: list[float],
    omega_starts_deg: list[float],
    y_step_sizes_um: list[float],
    y_steps: list[int],
    should_raise: bool,
):
    def make_params():
        GridParamsTest(
            x_start_um=0,
            y_starts_um=y_starts_um,
            z_starts_um=z_starts_um,
            omega_starts_deg=omega_starts_deg,
            y_step_sizes_um=y_step_sizes_um,
            y_steps=y_steps,
            sample_id=0,
            visit="/tmp",
            parameter_model_version=get_param_version(),
            file_name="/tmp",
            storage_directory="/tmp",
            x_steps=5,
        )

    if should_raise:
        with pytest.raises(
            ValidationError, match="Fields must all have the same length:"
        ):
            make_params()
    else:
        make_params()


class SpecifiedThreeDTest(SpecifiedThreeDGridScan):
    # Skip parent validation for easier testing
    def _check_lengths_are_same(self):  # type: ignore
        return self


@pytest.mark.parametrize(
    "y_starts_um, z_starts_um, omega_starts_deg, y_step_sizes_um, y_steps, should_raise",
    [
        ([1, 1, 1], [1, 1, 1], [1, 1, 1], [1, 1, 1], [1, 1, 1], True),
        ([1, 1], [1, 1], [1, 1], [1, 1, 1], [1, 1], True),
        ([1, 1], [1, 1], [1, 1, 1], [1, 1], [1, 1], True),
        ([1, 1], [1, 1], [1, 1], [1, 1], [1, 1], False),
    ],
)
def test_three_d_grid_scan_validation(
    y_starts_um: list[float],
    z_starts_um: list[float],
    omega_starts_deg: list[float],
    y_step_sizes_um: list[float],
    y_steps: list[int],
    should_raise: bool,
):
    def make_params():
        SpecifiedThreeDTest(
            x_start_um=0,
            y_starts_um=y_starts_um,
            z_starts_um=z_starts_um,
            omega_starts_deg=omega_starts_deg,
            y_step_sizes_um=y_step_sizes_um,
            y_steps=y_steps,
            sample_id=0,
            visit="/tmp",
            parameter_model_version=get_param_version(),
            file_name="/tmp",
            storage_directory="/tmp",
            x_steps=5,
        )

    if should_raise:
        with pytest.raises(ValidationError, match="must be length 2 for 3D scans"):
            make_params()
    else:
        make_params()
