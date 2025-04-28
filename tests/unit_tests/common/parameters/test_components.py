from contextlib import nullcontext as does_not_raise
from pathlib import Path

import pytest
from pydantic import ValidationError

from mx_bluesky.common.parameters.components import WithSnapshot


@pytest.mark.parametrize(
    "model, expectation",
    [
        [
            {
                "snapshot_directory": Path("/tmp"),
                "snapshot_omegas_deg": [],
                "use_grid_snapshots": False,
            },
            does_not_raise(),
        ],
        [
            {
                "snapshot_directory": Path("/tmp"),
                "snapshot_omegas_deg": [10, 20, 30, 40],
                "use_grid_snapshots": False,
            },
            does_not_raise(),
        ],
        [
            {
                "snapshot_directory": Path("/tmp"),
                "snapshot_omegas_deg": [0, 270],
                "use_grid_snapshots": True,
            },
            pytest.raises(ValidationError),
        ],
        [
            {
                "snapshot_directory": Path("/tmp"),
                "snapshot_omegas_deg": [0],
                "use_grid_snapshots": True,
            },
            pytest.raises(ValidationError),
        ],
        [
            {
                "snapshot_directory": Path("/tmp"),
                "snapshot_omegas_deg": [10, 80],
                "use_grid_snapshots": True,
            },
            pytest.raises(ValidationError),
        ],
        [
            {
                "snapshot_directory": Path("/tmp"),
                "use_grid_snapshots": True,
            },
            does_not_raise(),
        ],
    ],
)
def test_validate_with_snapshot_omegas_grid_snapshots(model, expectation):
    with expectation:
        WithSnapshot.model_validate(model)
