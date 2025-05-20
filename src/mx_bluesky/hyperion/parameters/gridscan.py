from __future__ import annotations

from dodal.devices.fast_grid_scan import (
    PandAGridScanParams,
    ZebraGridScanParams,
)

from mx_bluesky.common.parameters.gridscan import (
    GridCommon,
    SpecifiedThreeDGridScan,
)
from mx_bluesky.hyperion.parameters.components import WithHyperionUDCFeatures


class GridCommonWithHyperionDetectorParams(GridCommon, WithHyperionUDCFeatures):
    """Used by models which require detector parameters but have no specifications of the grid"""

    # These detector params only exist so that we can properly select enable_dev_shm. Remove in
    # https://github.com/DiamondLightSource/hyperion/issues/1395"""
    @property
    def detector_params(self):
        params = super().detector_params
        params.enable_dev_shm = (
            self.features.compare_cpu_and_gpu_zocalo or self.features.use_gpu_results
        )
        return params


class HyperionSpecifiedThreeDGridScan(WithHyperionUDCFeatures, SpecifiedThreeDGridScan):
    """Hyperion's 3D grid scan deviates from the common class due to: optionally using a PandA, optionally using dev_shm for GPU analysis, and using a config server for features"""

    # These detector params only exist so that we can properly select enable_dev_shm. Remove in
    # https://github.com/DiamondLightSource/hyperion/issues/1395"""

    @property
    def detector_params(self):
        params = super().detector_params
        params.enable_dev_shm = (
            self.features.compare_cpu_and_gpu_zocalo or self.features.use_gpu_results
        )
        return params

    # Relative to common grid scan, stub offsets are defined by config server
    @property
    def FGS_params(self) -> ZebraGridScanParams:
        return ZebraGridScanParams(
            x_steps=self.x_steps,
            y_steps=self.y_steps,
            z_steps=self.z_steps,
            x_step_size_mm=self.x_step_size_um / 1000,
            y_step_size_mm=self.y_step_size_um / 1000,
            z_step_size_mm=self.z_step_size_um / 1000,
            x_start_mm=self.x_start_um / 1000,
            y1_start_mm=self.y_start_um / 1000,
            z1_start_mm=self.z_start_um / 1000,
            y2_start_mm=self.y2_start_um / 1000,
            z2_start_mm=self.z2_start_um / 1000,
            set_stub_offsets=self.features.set_stub_offsets,
            dwell_time_ms=self.exposure_time_s * 1000,
            transmission_fraction=self.transmission_frac,
        )

    @property
    def panda_FGS_params(self) -> PandAGridScanParams:
        if self.y_steps % 2 and self.z_steps > 0:
            # See https://github.com/DiamondLightSource/hyperion/issues/1118 for explanation
            raise OddYStepsException(
                "The number of Y steps must be even for a PandA gridscan"
            )
        return PandAGridScanParams(
            x_steps=self.x_steps,
            y_steps=self.y_steps,
            z_steps=self.z_steps,
            x_step_size_mm=self.x_step_size_um / 1000,
            y_step_size_mm=self.y_step_size_um / 1000,
            z_step_size_mm=self.z_step_size_um / 1000,
            x_start_mm=self.x_start_um / 1000,
            y1_start_mm=self.y_start_um / 1000,
            z1_start_mm=self.z_start_um / 1000,
            y2_start_mm=self.y2_start_um / 1000,
            z2_start_mm=self.z2_start_um / 1000,
            set_stub_offsets=self.features.set_stub_offsets,
            run_up_distance_mm=self.panda_runup_distance_mm,
            transmission_fraction=self.transmission_frac,
        )


class OddYStepsException(Exception): ...


class PinTipCentreThenXrayCentre(
    GridCommonWithHyperionDetectorParams, WithHyperionUDCFeatures
):
    tip_offset_um: float = 0


class GridScanWithEdgeDetect(
    GridCommonWithHyperionDetectorParams, WithHyperionUDCFeatures
):
    pass
