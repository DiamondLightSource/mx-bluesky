from typing import TypeVar

from pydantic import BaseModel, model_validator

from mx_bluesky.common.parameters.components import (
    MxBlueskyParameters,
    WithSample,
    WithVisit,
)
from mx_bluesky.common.parameters.gridscan import (
    RobotLoadThenCentre,
)
from mx_bluesky.hyperion.parameters.rotation import MultiRotationScan

T = TypeVar("T", bound=BaseModel)


def construct_from_values(parent_context: dict, key: str, t: type[T]) -> T:
    values = dict(parent_context)
    values |= values[key]
    return t(**values)


class LoadCentreCollect(MxBlueskyParameters, WithVisit, WithSample):
    """Experiment parameters to perform the combined robot load,
    pin-tip centre and rotation scan operations."""

    robot_load_then_centre: RobotLoadThenCentre
    multi_rotation_scan: MultiRotationScan

    @model_validator(mode="before")
    @classmethod
    def validate_model(cls, values):
        allowed_keys = (
            LoadCentreCollect.model_fields.keys()
            | RobotLoadThenCentre.model_fields.keys()
            | MultiRotationScan.model_fields.keys()
        )
        disallowed_keys = values.keys() - allowed_keys
        assert (
            disallowed_keys == set()
        ), f"Unexpected fields found in LoadCentreCollect {disallowed_keys}"

        values["robot_load_then_centre"] = construct_from_values(
            values, "robot_load_then_centre", RobotLoadThenCentre
        )
        values["multi_rotation_scan"] = construct_from_values(
            values, "multi_rotation_scan", MultiRotationScan
        )
        return values
