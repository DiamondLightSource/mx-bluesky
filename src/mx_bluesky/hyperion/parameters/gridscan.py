from __future__ import annotations

from dodal.devices.detector import DetectorParams
from dodal.devices.fast_grid_scan import (
    PandAGridScanParams,
    ZebraGridScanParamsThreeD,
)
from pydantic import Field

from mx_bluesky.common.parameters.components import (
    DiffractionExperiment,
    DiffractionExperimentWithSample,
    IspybExperimentType,
    OptionalGonioAngleStarts,
)
from mx_bluesky.common.parameters.gridscan import (
    GridDetectionParams,
    GridScanParams,
    create_detector_params_for_grid_scan,
)
from mx_bluesky.hyperion.external_interaction.config_server import (
    get_hyperion_feature_settings,
)


def create_detector_params_for_grid_scan_with_hyperion_feature_settings(
    params: DiffractionExperiment,
) -> DetectorParams:
    detector_params = create_detector_params_for_grid_scan(params)
    detector_params.enable_dev_shm = get_hyperion_feature_settings().USE_GPU_RESULTS
    return detector_params


# Relative to common grid scan, stub offsets are defined by config server
def fast_gridscan_params(
    expt_params: DiffractionExperiment, grid_scan_params: GridScanParams
) -> ZebraGridScanParamsThreeD:
    """During 3D grid scans, there is an omega rotation before the second grid,
    transforming Y -> Z axes, so use the second element of the Y params to set
    Z params on the 3D grid scan device.
    """
    return ZebraGridScanParamsThreeD(
        x_steps=grid_scan_params.x_steps,
        y_steps=grid_scan_params.y_steps[0],
        z_steps=grid_scan_params.y_steps[1],
        x_step_size_mm=grid_scan_params.x_step_size_um / 1000,
        y_step_size_mm=grid_scan_params.y_step_sizes_um[0] / 1000,
        z_step_size_mm=grid_scan_params.y_step_sizes_um[1] / 1000,
        x_start_mm=grid_scan_params.x_start_um / 1000,
        y1_start_mm=grid_scan_params.y_starts_um[0] / 1000,
        z1_start_mm=grid_scan_params.z_starts_um[0] / 1000,
        y2_start_mm=grid_scan_params.y_starts_um[1] / 1000,
        z2_start_mm=grid_scan_params.z_starts_um[1] / 1000,
        set_stub_offsets=get_hyperion_feature_settings().SET_STUB_OFFSETS,
        dwell_time_ms=expt_params.exposure_time_s * 1000,
        transmission_fraction=expt_params.transmission_frac,
    )


def panda_fast_gridscan_params(
    expt_params: DiffractionExperiment, grid_scan_params: GridScanParams
) -> PandAGridScanParams:
    if grid_scan_params.y_steps[0] % 2 and grid_scan_params.y_steps[1] > 0:
        # See https://github.com/DiamondLightSource/hyperion/issues/1118 for explanation
        raise OddYStepsError("The number of Y steps must be even for a PandA gridscan")
    return PandAGridScanParams(
        x_steps=grid_scan_params.x_steps,
        y_steps=grid_scan_params.y_steps[0],
        z_steps=grid_scan_params.y_steps[1],
        x_step_size_mm=grid_scan_params.x_step_size_um / 1000,
        y_step_size_mm=grid_scan_params.y_step_sizes_um[0] / 1000,
        z_step_size_mm=grid_scan_params.y_step_sizes_um[1] / 1000,
        x_start_mm=grid_scan_params.x_start_um / 1000,
        y1_start_mm=grid_scan_params.y_starts_um[0] / 1000,
        z1_start_mm=grid_scan_params.z_starts_um[0] / 1000,
        y2_start_mm=grid_scan_params.y_starts_um[1] / 1000,
        z2_start_mm=grid_scan_params.z_starts_um[1] / 1000,
        set_stub_offsets=get_hyperion_feature_settings().SET_STUB_OFFSETS,
        run_up_distance_mm=get_hyperion_feature_settings().PANDA_RUNUP_DISTANCE_MM,
        transmission_fraction=expt_params.transmission_frac,
    )


class OddYStepsError(Exception): ...


class PinTipCentreThenXrayCentre(
    DiffractionExperimentWithSample, GridDetectionParams, OptionalGonioAngleStarts
):
    # Override the default field type
    ispyb_experiment_type: IspybExperimentType = Field(
        default=IspybExperimentType.GRIDSCAN_3D
    )

    tip_offset_um: float = 0
