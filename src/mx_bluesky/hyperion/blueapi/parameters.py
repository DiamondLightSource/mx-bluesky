"""
This module contains the parameter models exported via the hyperion-blueapi REST interface.
"""

from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, Field
from pydantic.config import ConfigDict

from mx_bluesky.common.parameters.components import (
    get_param_version,
)
from mx_bluesky.common.parameters.constants import GridscanParamConstants
from mx_bluesky.hyperion.blueapi.mixins import WithCentreSelection
from mx_bluesky.hyperion.parameters.constants import HyperionConstants
from mx_bluesky.hyperion.parameters.gridscan import PinTipCentreThenXrayCentre
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect


class HyperionParam(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SingleSamplePinTypeParam(BaseModel):
    name: Literal["ssp"] = "ssp"
    wells: Literal[1] = Field(exclude=True, default=1)


class MultiSamplePinTypeParam(BaseModel):
    name: Literal["msp"] = "msp"
    wells: int
    well_size_um: float
    tip_to_first_well_um: float


PinTypeParam: TypeAlias = SingleSamplePinTypeParam | MultiSamplePinTypeParam


class RobotLoadThenCentreParams(HyperionParam):
    storage_directory: str
    file_name: str
    transmission_frac: float
    exposure_time_s: float
    omega_start_deg: float
    chi_start_deg: float
    pin_type: SingleSamplePinTypeParam | MultiSamplePinTypeParam = Field(
        discriminator="name", default=SingleSamplePinTypeParam()
    )


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
    tip_offset, grid_width = pin_type_to_tip_offset_and_grid_width(
        external_params.robot_load_then_centre.pin_type
    )
    params_as_dict["robot_load_then_centre"]["grid_width_um"] = grid_width
    params_as_dict["robot_load_then_centre"]["tip_offset_um"] = tip_offset
    del params_as_dict["robot_load_then_centre"]["pin_type"]

    return LoadCentreCollect(**params_as_dict)


def pin_tip_centre_then_xray_centre_to_internal(
    visit: str,
    storage_directory: str,
    sample_id: int,
    sample_puck: int,
    sample_pin: int,
) -> PinTipCentreThenXrayCentre:
    params_as_dict: dict[str, Any] = {
        "visit": visit,
        "storage_directory": storage_directory,
    }
    params_as_dict["file_name"] = "xrc"
    params_as_dict["parameter_model_version"] = get_param_version()
    params_as_dict["demand_energy_ev"] = None
    # TODO sample_id must not be none?
    params_as_dict["sample_id"] = sample_id
    params_as_dict["sample_puck"] = sample_puck
    params_as_dict["sample_pin"] = sample_pin
    params_as_dict["detector_distance_mm"] = (
        HyperionConstants.DEFAULT_DETECTOR_DISTANCE_MM
    )
    tip_offset, grid_width = pin_type_to_tip_offset_and_grid_width(
        SingleSamplePinTypeParam()
    )
    params_as_dict["tip_offset_um"] = tip_offset
    params_as_dict["grid_width_um"] = grid_width
    params_as_dict["exposure_time_s"] = GridscanParamConstants.EXPOSURE_TIME_S
    params_as_dict["transmission_frac"] = 1.0

    # gonio pos is as found
    return PinTipCentreThenXrayCentre(**params_as_dict)


def pin_type_to_tip_offset_and_grid_width(
    pin_type: PinTypeParam,
) -> tuple[float, float]:
    """
    Obtain the tip offset and grid width for the given pin type.

    The grid width is the "width" of the area where there may be samples and is used
    to construct the grid for gridscans.

    From a pin perspective this is along the length of the pin but we use width here as
    we mount the sample at 90 deg to the optical camera.

    We calculate the full width by adding all the gaps between wells then assuming
    there is a buffer of {tip_to_first_well_um} either side too. In reality the
    calculation does not need to be very exact as long as we get a width that's good
    enough to use for optical centring and XRC grid size.

    Args:
        pin_type (PinTypeParam): The pin type which may describe a single or multi sample pin
    Returns:
        tuple[float, float]: the tip offset, which is used for the pin-tip detection initial
        positioning, and the grid width.
    """
    match pin_type:
        case SingleSamplePinTypeParam():
            return (
                GridscanParamConstants.PIN_WIDTH_UM / 2,
                GridscanParamConstants.PIN_WIDTH_UM,
            )
        case MultiSamplePinTypeParam() as pin_type:
            full_width = (
                pin_type.wells - 1
            ) * pin_type.well_size_um + 2 * pin_type.tip_to_first_well_um
            return full_width / 2, full_width
    raise ValueError(f"Unexpected pin type {pin_type}")
