from dodal.devices.detector.detector import DetectorParams
from pydantic import Field

from mx_bluesky.common.parameters.components import (
    MxBlueskyParameters,
    WithOptionalEnergyChange,
    WithSample,
    WithSnapshot,
    WithVisit,
)
from mx_bluesky.common.parameters.constants import (
    HardwareConstants,
)
from mx_bluesky.hyperion.parameters.components import WithHyperionUDCFeatures
from mx_bluesky.hyperion.parameters.constants import CONST, I03Constants
from mx_bluesky.hyperion.parameters.gridscan import (
    GridCommonWithHyperionDetectorParams,
    PinTipCentreThenXrayCentre,
)


class RobotLoadAndEnergyChange(
    MxBlueskyParameters, WithSample, WithSnapshot, WithOptionalEnergyChange, WithVisit
):
    thawing_time: float = Field(default=HardwareConstants.THAWING_TIME)


class RobotLoadThenCentre(
    GridCommonWithHyperionDetectorParams, WithHyperionUDCFeatures
):
    thawing_time: float = Field(default=HardwareConstants.THAWING_TIME)
    tip_offset_um: float = Field(default=HardwareConstants.TIP_OFFSET_UM)

    # These detector params only exist so that we can properly select enable_dev_shm. Remove in
    # https://github.com/DiamondLightSource/hyperion/issues/1395"""
    @property
    def detector_params(self) -> DetectorParams:
        self.det_dist_to_beam_converter_path = (
            self.det_dist_to_beam_converter_path
            or CONST.PARAM.DETECTOR.BEAM_XY_LUT_PATH
        )
        optional_args = {}
        if self.run_number:
            optional_args["run_number"] = self.run_number
        assert self.detector_distance_mm is not None, (
            "Detector distance must be filled before generating DetectorParams"
        )
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
        )

    @property
    def robot_load_params(self) -> RobotLoadAndEnergyChange:
        my_params = self.model_dump()
        return RobotLoadAndEnergyChange(**my_params)

    @property
    def pin_centre_then_xray_centre_params(self) -> PinTipCentreThenXrayCentre:
        my_params = self.model_dump()
        del my_params["thawing_time"]
        return PinTipCentreThenXrayCentre(**my_params)
