"""
This module contains the parameter models exported via the hyperion-blueapi REST interface.
"""

from pydantic import BaseModel
from pydantic.config import ConfigDict

from mx_bluesky.common.parameters.components import (
    get_param_version,
)
from mx_bluesky.hyperion.blueapi.mixins import WithCentreSelection
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect


class HyperionParam(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RobotLoadThenCentreParams(HyperionParam):
    storage_directory: str
    file_name: str
    transmission_frac: float
    exposure_time_s: float
    omega_start_deg: float
    chi_start_deg: float
    tip_offset_um: float
    grid_width_um: float


class SingleRotationScanParams(HyperionParam):
    omega_start_deg: float
    phi_start_deg: float
    chi_start_deg: float
    rotation_direction: str
    scan_width_deg: float


class MultiRotationScanParams(HyperionParam):
    comment: str
    file_name: str
    storage_directory: str
    exposure_time_s: float
    rotation_increment_deg: float
    snapshot_omegas_deg: list[float]
    rotation_scans: list[SingleRotationScanParams]
    transmission_frac: float
    ispyb_experiment_type: str


class LoadCentreCollectParams(WithCentreSelection, HyperionParam):
    """This model is exposed as the BlueAPI REST parameter model for Hyperion Collections.
    It can represent the full range of operations that are supported by LoadCentreCollect;
    this is a superset of the operations that are actually required to follow Agamemnon instructions.

    This is intended to provide additional flexibility to allow a potential future point of configuration
    where the supervisor can supply default values for values not explicitly specified by Agamemnon,
    also to allow future exposure of this BlueAPI plan for e.g. commissioning purposes.
    This may also permit the supervisor to implement future functionality by adjusting these parameters.
    """

    visit: str
    detector_distance_mm: float
    sample_id: int
    sample_puck: int
    sample_pin: int
    demand_energy_ev: float
    robot_load_then_centre: RobotLoadThenCentreParams
    multi_rotation_scan: MultiRotationScanParams


def load_centre_collect_to_internal(
    external_params: LoadCentreCollectParams,
) -> LoadCentreCollect:
    params_as_dict = external_params.model_dump()
    params_as_dict["parameter_model_version"] = get_param_version()
    return LoadCentreCollect(**params_as_dict)
