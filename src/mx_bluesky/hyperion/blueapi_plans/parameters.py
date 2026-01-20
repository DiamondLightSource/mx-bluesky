"""The big dumb blueapi parameter model for LoadCentreCollect"""

from pydantic import BaseModel
from pydantic.config import ConfigDict

from mx_bluesky.common.parameters.components import (
    WithCentreSelection,
    get_param_version,
)
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect


class HyperionParam(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RobotLoadThenCentreParams(HyperionParam):
    storage_directory: str
    file_name: str
    demand_energy_ev: float
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
    demand_energy_ev: float
    exposure_time_s: float
    rotation_increment_deg: float
    snapshot_omegas_deg: list[float]
    rotation_scans: list[SingleRotationScanParams]
    transmission_frac: float
    ispyb_experiment_type: str


class LoadCentreCollectParams(WithCentreSelection, HyperionParam):
    visit: str
    detector_distance_mm: float
    sample_id: int
    sample_puck: int
    sample_pin: int
    robot_load_then_centre: RobotLoadThenCentreParams
    multi_rotation_scan: MultiRotationScanParams


def load_centre_collect_to_internal(
    external_params: LoadCentreCollectParams,
) -> LoadCentreCollect:
    params_as_dict = external_params.model_dump()
    params_as_dict["parameter_model_version"] = get_param_version()
    return LoadCentreCollect(**params_as_dict)
