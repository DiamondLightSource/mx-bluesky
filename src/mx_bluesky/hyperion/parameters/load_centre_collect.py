from typing import Self, TypeVar

from pydantic import BaseModel, model_validator

from mx_bluesky.common.parameters.components import (
    MxBlueskyParameters,
    WithCentreSelection,
    WithSample,
    WithVisit,
)
from mx_bluesky.hyperion.parameters.components import WithHyperionUDCFeatures
from mx_bluesky.hyperion.parameters.robot_load import (
    RobotLoadThenCentre,
)
from mx_bluesky.hyperion.parameters.rotation import MultiRotationScan

T = TypeVar("T", bound=BaseModel)


def construct_from_values(parent_context: dict, child_dict: dict, t: type[T]) -> T:
    values = {k: v for k, v in parent_context.items() if not isinstance(v, dict)}
    values |= child_dict
    return t(**values)


class LoadCentreCollect(
    MxBlueskyParameters,
    WithVisit,
    WithSample,
    WithCentreSelection,
    WithHyperionUDCFeatures,
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
        assert disallowed_keys == set(), (
            f"Unexpected fields found in LoadCentreCollect {disallowed_keys}"
        )

        keys_from_outer_load_centre_collect = (
            MxBlueskyParameters.model_fields.keys()
            | WithSample.model_fields.keys()
            | WithVisit.model_fields.keys()
        )
        duplicated_robot_load_then_centre_keys = (
            keys_from_outer_load_centre_collect
            & values["robot_load_then_centre"].keys()
        )
        assert not (duplicated_robot_load_then_centre_keys), (
            f"Unexpected keys in robot_load_then_centre: {', '.join(duplicated_robot_load_then_centre_keys)}"
        )

        duplicated_multi_rotation_scan_keys = (
            keys_from_outer_load_centre_collect & values["multi_rotation_scan"].keys()
        )
        assert not (duplicated_multi_rotation_scan_keys), (
            f"Unexpected keys in multi_rotation_scan: {', '.join(duplicated_multi_rotation_scan_keys)}"
        )

        new_robot_load_then_centre_params = construct_from_values(
            values, values["robot_load_then_centre"], RobotLoadThenCentre
        )
        new_multi_rotation_scan_params = construct_from_values(
            values, values["multi_rotation_scan"], MultiRotationScan
        )
        values["multi_rotation_scan"] = new_multi_rotation_scan_params
        values["robot_load_then_centre"] = new_robot_load_then_centre_params
        return values

    @model_validator(mode="after")
    def _check_rotation_start_xyz_is_not_specified(self) -> Self:
        for scan in self.multi_rotation_scan.single_rotation_scans:
            assert (
                not scan.x_start_um and not scan.y_start_um and not scan.z_start_um
            ), (
                "Specifying start xyz for sweeps is not supported in combination with centring."
            )
        return self

    @model_validator(mode="after")
    def _check_different_gridscan_and_rotation_energy_not_specified(self) -> Self:
        assert (
            self.multi_rotation_scan.demand_energy_ev is None
            or self.multi_rotation_scan.demand_energy_ev
            == self.robot_load_then_centre.demand_energy_ev
        ), "Setting a different energy for gridscan and rotation is not supported."
        return self
