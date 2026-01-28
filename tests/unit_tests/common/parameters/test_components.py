from contextlib import nullcontext as does_not_raise
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from mx_bluesky.common.parameters.components import (
    MxBlueskyParameters,
    WithSnapshot,
    get_param_version,
)


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
                "snapshot_omegas_deg": [],
                "use_grid_snapshots": True,
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


class PlainModel(MxBlueskyParameters):
    outer_path: Path


class InnerModel(BaseModel):
    inner_path: Path


class NestedModel(MxBlueskyParameters):
    outer_path: Path
    inner_model: InnerModel


def test_mx_bluesky_parameters_round_trip_python():
    params = MxBlueskyParameters(parameter_model_version=get_param_version())
    serialized_model = params.model_dump()
    new_params = MxBlueskyParameters.model_validate(serialized_model)
    assert new_params == params


def test_mx_bluesky_parameters_path_round_trip_python():
    params = PlainModel(
        parameter_model_version=get_param_version(), outer_path=Path("/tmp")
    )
    serialized_model = params.model_dump()
    new_params = PlainModel.model_validate(serialized_model)
    assert new_params == params


def test_mx_bluesky_parameters_nested_path_round_trip_python():
    params = NestedModel(
        parameter_model_version=get_param_version(),
        outer_path=Path("/tmp"),
        inner_model=InnerModel(inner_path=Path("/tmp")),
    )
    serialized_model = params.model_dump()
    new_params = NestedModel.model_validate(serialized_model)
    assert new_params == params


def test_mx_bluesky_parameters_round_trip_json():
    params = MxBlueskyParameters(parameter_model_version=get_param_version())
    serialized_model = params.model_dump_json()
    new_params = MxBlueskyParameters.model_validate_json(serialized_model)
    assert new_params == params
