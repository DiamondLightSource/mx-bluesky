from __future__ import annotations

from dodal.devices.detector import (
    DetectorParams,
)
from dodal.devices.fast_grid_scan import (
    PandAGridScanParams,
    ZebraGridScanParams,
)
from pydantic import Field, PrivateAttr
from scanspec.core import Path as ScanPath
from scanspec.specs import Line, Static

from mx_bluesky.common.parameters.components import (
    SplitScan,
    WithOptionalEnergyChange,
    WithPandaGridScan,
)
from mx_bluesky.common.parameters.gridscan import (
    GridCommon,
    SpecifiedGrid,
)
from mx_bluesky.hyperion.parameters.components import WithHyperionFeatures
from mx_bluesky.hyperion.parameters.constants import CONST, I03Constants


class HyperionGridCommon(GridCommon, WithHyperionFeatures):
    # This class only exists so that we can properly select enable_dev_shm. Remove in
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


class HyperionThreeDGridScan(
    HyperionGridCommon,
    SpecifiedGrid,
    SplitScan,
    WithOptionalEnergyChange,
    WithPandaGridScan,
):
    """Parameters representing a so-called 3D grid scan, which consists of doing a
    gridscan in X and Y, followed by one in X and Z."""

    grid1_omega_deg: float = Field(default=CONST.PARAM.GRIDSCAN.OMEGA_1)  # type: ignore
    grid2_omega_deg: float = Field(default=CONST.PARAM.GRIDSCAN.OMEGA_2)
    x_step_size_um: float = Field(default=CONST.PARAM.GRIDSCAN.BOX_WIDTH_UM)
    y_step_size_um: float = Field(default=CONST.PARAM.GRIDSCAN.BOX_WIDTH_UM)
    z_step_size_um: float = Field(default=CONST.PARAM.GRIDSCAN.BOX_WIDTH_UM)
    y2_start_um: float
    z2_start_um: float
    x_steps: int = Field(gt=0)
    y_steps: int = Field(gt=0)
    z_steps: int = Field(gt=0)
    _set_stub_offsets: bool = PrivateAttr(default_factory=lambda: False)

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

    def do_set_stub_offsets(self, value: bool):
        self._set_stub_offsets = value

    @property
    def grid_1_spec(self):
        x_end = self.x_start_um + self.x_step_size_um * (self.x_steps - 1)
        y1_end = self.y_start_um + self.y_step_size_um * (self.y_steps - 1)
        grid_1_x = Line("sam_x", self.x_start_um, x_end, self.x_steps)
        grid_1_y = Line("sam_y", self.y_start_um, y1_end, self.y_steps)
        grid_1_z = Static("sam_z", self.z_start_um)
        return grid_1_y.zip(grid_1_z) * ~grid_1_x

    @property
    def grid_2_spec(self):
        x_end = self.x_start_um + self.x_step_size_um * (self.x_steps - 1)
        z2_end = self.z2_start_um + self.z_step_size_um * (self.z_steps - 1)
        grid_2_x = Line("sam_x", self.x_start_um, x_end, self.x_steps)
        grid_2_z = Line("sam_z", self.z2_start_um, z2_end, self.z_steps)
        grid_2_y = Static("sam_y", self.y2_start_um)
        return grid_2_z.zip(grid_2_y) * ~grid_2_x

    @property
    def scan_indices(self):
        """The first index of each gridscan, useful for writing nexus files/VDS"""
        return [
            0,
            len(ScanPath(self.grid_1_spec.calculate()).consume().midpoints["sam_x"]),
        ]

    @property
    def scan_spec(self):
        """A fully specified ScanSpec object representing both grids, with x, y, z and
        omega positions."""
        return self.grid_1_spec.concat(self.grid_2_spec)

    @property
    def scan_points(self):
        """A list of all the points in the scan_spec."""
        return ScanPath(self.scan_spec.calculate()).consume().midpoints

    @property
    def scan_points_first_grid(self):
        """A list of all the points in the first grid scan."""
        return ScanPath(self.grid_1_spec.calculate()).consume().midpoints

    @property
    def scan_points_second_grid(self):
        """A list of all the points in the second grid scan."""
        return ScanPath(self.grid_2_spec.calculate()).consume().midpoints

    @property
    def num_images(self) -> int:
        return len(self.scan_points["sam_x"])


class OddYStepsException(Exception): ...
