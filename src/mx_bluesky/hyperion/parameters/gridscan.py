from __future__ import annotations

import os

from dodal.devices.detector import (
    DetectorParams,
)
from dodal.devices.fast_grid_scan import (
    PandAGridScanParams,
    ZebraGridScanParams,
)

from mx_bluesky.common.parameters.components import (
    SplitScan,
    WithOptionalEnergyChange,
    WithPandaGridScan,
)
from mx_bluesky.common.parameters.gridscan import (
    SpecifiedGrid,
    ThreeDGridScan,
)
from mx_bluesky.hyperion.parameters.components import WithHyperionFeatures
from mx_bluesky.hyperion.parameters.constants import CONST, I03Constants


class HyperionThreeDGridScan(
    ThreeDGridScan,
    SpecifiedGrid,
    SplitScan,
    WithOptionalEnergyChange,
    WithPandaGridScan,
    WithHyperionFeatures,
):
    """Hyperion's 3D grid scan varies from the common class due to: optionally using a PandA, optionally using dev_shm for GPU analysis, and using a config server for features"""

    # These detector params only exist so that we can properly select enable_dev_shm. Remove in
    # https://github.com/DiamondLightSource/hyperion/issues/1395"""
    @property
    def detector_params(self):
        self.det_dist_to_beam_converter_path = (
            self.det_dist_to_beam_converter_path
            or CONST.PARAM.DETECTOR.BEAM_XY_LUT_PATH
        )
        optional_args = {}
        if self.run_number:
            optional_args["run_number"] = self.run_number
        assert (
            self.detector_distance_mm is not None
        ), "Detector distance must be filled before generating DetectorParams"
        os.makedirs(self.storage_directory, exist_ok=True)
        return DetectorParams(
            detector_size_constants=I03Constants.DETECTOR,
            expected_energy_ev=self.demand_energy_ev,
            exposure_time=self.exposure_time_s,
            directory=self.storage_directory,
            prefix=self.file_name,
            detector_distance=self.detector_distance_mm,
            omega_start=self.omega_start_deg or 0,
            omega_increment=0,
            num_images_per_trigger=1,
            num_triggers=self.num_images,
            use_roi_mode=self.use_roi_mode,
            det_dist_to_beam_converter_path=self.det_dist_to_beam_converter_path,
            trigger_mode=self.trigger_mode,
            enable_dev_shm=self.features.compare_cpu_and_gpu_zocalo,
            **optional_args,
        )

    # Relative to common grid scan, stub offsets are defined by config server
    @property
    def FGS_params(self) -> ZebraGridScanParams:
        return ZebraGridScanParams(
            x_steps=self.x_steps,
            y_steps=self.y_steps,
            z_steps=self.z_steps,
            x_step_size=self.x_step_size_um,
            y_step_size=self.y_step_size_um,
            z_step_size=self.z_step_size_um,
            x_start=self.x_start_um,
            y1_start=self.y_start_um,
            z1_start=self.z_start_um,
            y2_start=self.y2_start_um,
            z2_start=self.z2_start_um,
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
            x_step_size=self.x_step_size_um,
            y_step_size=self.y_step_size_um,
            z_step_size=self.z_step_size_um,
            x_start=self.x_start_um,
            y1_start=self.y_start_um,
            z1_start=self.z_start_um,
            y2_start=self.y2_start_um,
            z2_start=self.z2_start_um,
            set_stub_offsets=self.features.set_stub_offsets,
            run_up_distance_mm=self.panda_runup_distance_mm,
            transmission_fraction=self.transmission_frac,
        )


class OddYStepsException(Exception): ...
