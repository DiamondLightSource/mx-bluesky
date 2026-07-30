from __future__ import annotations

from dodal.devices.aperturescatterguard import ApertureValue
from dodal.devices.detector import DetectorParams
from pydantic import Field

from mx_bluesky.common.parameters.components import (
    DiffractionExperiment,
    DiffractionExperimentWithSample,
    IspybExperimentType,
    OptionalGonioAngleStarts,
)
from mx_bluesky.common.parameters.constants import GridscanParamConstants
from mx_bluesky.common.parameters.gridscan import (
    GridDetectionParams,
    create_detector_params_for_grid_scan,
)
from mx_bluesky.hyperion.external_interaction.config_server import (
    get_hyperion_feature_settings,
)


# TODO Move these device-level parameter builders out of this module as they are not part of the mx-bluesky
# parameter model. https://github.com/DiamondLightSource/mx-bluesky/issues/1793
def create_detector_params_for_grid_scan_with_hyperion_feature_settings(
    params: DiffractionExperiment,
) -> DetectorParams:
    detector_params = create_detector_params_for_grid_scan(params)
    detector_params.enable_dev_shm = get_hyperion_feature_settings().USE_GPU_RESULTS
    return detector_params


class PinTipCentreThenXrayCentre(
    DiffractionExperimentWithSample, GridDetectionParams, OptionalGonioAngleStarts
):
    # Overrides of defaults in superclasses
    exposure_time_s: float = Field(default=GridscanParamConstants.EXPOSURE_TIME_S)
    ispyb_experiment_type: IspybExperimentType = Field(
        default=IspybExperimentType.GRIDSCAN_3D
    )
    selected_aperture: ApertureValue | None = Field(default=ApertureValue.SMALL)
    tip_offset_um: float = 0
