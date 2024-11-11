from __future__ import annotations

import os

from dodal.devices.aperturescatterguard import ApertureValue
from dodal.devices.detector import (
    DetectorParams,
)
from pydantic import Field

from mx_bluesky.common.parameters.components import (
    DiffractionExperimentWithSample,
    IspybExperimentType,
    OptionalGonioAngleStarts,
    WithScan,
    XyzStarts,
)
from mx_bluesky.common.parameters.constants import (
    DetectorParamConstants,
    GridscanParamConstants,
    HardwareConstants,
)
from mx_bluesky.common.parameters.robot_load import RobotLoadAndEnergyChange


class GridCommon(
    DiffractionExperimentWithSample,
    OptionalGonioAngleStarts,
):
    grid_width_um: float = Field(default=GridscanParamConstants.WIDTH_UM)
    exposure_time_s: float = Field(default=GridscanParamConstants.EXPOSURE_TIME_S)
    use_roi_mode: bool = Field(default=GridscanParamConstants.USE_ROI)

    ispyb_experiment_type: IspybExperimentType = Field(
        default=IspybExperimentType.GRIDSCAN_3D
    )
    selected_aperture: ApertureValue | None = Field(default=ApertureValue.SMALL)

    @property
    def detector_params(self):
        self.det_dist_to_beam_converter_path = (
            self.det_dist_to_beam_converter_path
            or DetectorParamConstants.BEAM_XY_LUT_PATH
        )
        optional_args = {}
        if self.run_number:
            optional_args["run_number"] = self.run_number
        assert (
            self.detector_distance_mm is not None
        ), "Detector distance must be filled before generating DetectorParams"
        os.makedirs(self.storage_directory, exist_ok=True)
        return DetectorParams(
            detector_size_constants=DetectorParamConstants.DETECTOR,
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
            **optional_args,
        )


class RobotLoadThenCentre(GridCommon):
    thawing_time: float = Field(default=HardwareConstants.THAWING_TIME)

    def robot_load_params(self):
        my_params = self.model_dump()
        return RobotLoadAndEnergyChange(**my_params)

    def pin_centre_then_xray_centre_params(self):
        my_params = self.model_dump()
        del my_params["thawing_time"]
        return PinTipCentreThenXrayCentre(**my_params)


class GridScanWithEdgeDetect(GridCommon):
    box_size_um: float = Field(default=GridscanParamConstants.BOX_WIDTH_UM)


class PinTipCentreThenXrayCentre(GridCommon):
    tip_offset_um: float = 0


class SpecifiedGrid(XyzStarts, WithScan):
    """A specified grid is one which has defined values for the start position,
    grid and box sizes, etc., as opposed to parameters for a plan which will create
    those parameters at some point (e.g. through optical pin detection)."""
