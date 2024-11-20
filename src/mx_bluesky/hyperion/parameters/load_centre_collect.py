from typing import TypeVar

from pydantic import BaseModel, model_validator

from mx_bluesky.common.parameters.components import (
    MxBlueskyParameters,
    WithCentreSelection,
    WithSample,
    WithVisit,
)
from mx_bluesky.common.parameters.gridscan import (
    RobotLoadThenCentre,
)
from mx_bluesky.hyperion.parameters.rotation import MultiRotationScan

T = TypeVar("T", bound=BaseModel)


def construct_from_values(parent_context: dict, child_dict: dict, t: type[T]) -> T:
    values = {k: v for k, v in parent_context.items() if not isinstance(v, dict)}
    values |= child_dict
    return t(**values)


class LoadCentreCollect(
    MxBlueskyParameters, WithVisit, WithSample, WithCentreSelection
):
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

        new_robot_load_then_centre_params = construct_from_values(
            values, values["robot_load_then_centre"], RobotLoadThenCentre
        )
        new_multi_rotation_scan_params = construct_from_values(
            values, values["multi_rotation_scan"], MultiRotationScan
        )
        values["multi_rotation_scan"] = new_multi_rotation_scan_params
        values["robot_load_then_centre"] = new_robot_load_then_centre_params
        return values
