from __future__ import annotations

from dodal.devices.aperturescatterguard import ApertureValue
from dodal.devices.detector.det_dim_constants import EIGER2_X_9M_SIZE, EIGER2_X_16M_SIZE
from dodal.devices.detector.detector import DetectorParams
from dodal.devices.fast_grid_scan import (
    ZebraGridScanParams,
)
from dodal.utils import get_beamline_name
from pydantic import Field, PrivateAttr
from scanspec.core import Path as ScanPath
from scanspec.specs import Line, Static

from mx_bluesky.common.parameters.components import (
    DiffractionExperimentWithSample,
    IspybExperimentType,
    OptionalGonioAngleStarts,
    SplitScan,
    WithOptionalEnergyChange,
    WithScan,
    XyzStarts,
)
from mx_bluesky.common.parameters.constants import (
    DetectorParamConstants,
    GridscanParamConstants,
    HardwareConstants,
)

DETECTOR_SIZE_PER_BEAMLINE = {
    "i02-1": EIGER2_X_9M_SIZE,
    "dev": EIGER2_X_16M_SIZE,
    "i03": EIGER2_X_16M_SIZE,
}


class GridCommon(
    DiffractionExperimentWithSample,
    OptionalGonioAngleStarts,
):
    """
    Parameters used in every MX diffraction experiment using grids. This model should
    be used by plans which have no knowledge of the grid specifications - i.e before
    automatic grid detection has completed
    """

    box_size_um: float = Field(default=GridscanParamConstants.BOX_WIDTH_UM)
    grid_width_um: float = Field(default=GridscanParamConstants.WIDTH_UM)
    exposure_time_s: float = Field(default=GridscanParamConstants.EXPOSURE_TIME_S)

    ispyb_experiment_type: IspybExperimentType = Field(
        default=IspybExperimentType.GRIDSCAN_3D
    )
    selected_aperture: ApertureValue | None = Field(default=ApertureValue.SMALL)

    tip_offset_um: float = Field(default=HardwareConstants.TIP_OFFSET_UM)

    @property
    def detector_params(self):
        self.det_dist_to_beam_converter_path = (
            self.det_dist_to_beam_converter_path
            or DetectorParamConstants.BEAM_XY_LUT_PATH
        )
        optional_args = {}
        if self.run_number:
            optional_args["run_number"] = self.run_number
        assert self.detector_distance_mm is not None, (
            "Detector distance must be filled before generating DetectorParams"
        )
        return DetectorParams(
            detector_size_constants=DETECTOR_SIZE_PER_BEAMLINE[
                get_beamline_name("dev")
            ],
            expected_energy_ev=self.demand_energy_ev,
            exposure_time_s=self.exposure_time_s,
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


class SpecifiedGrid(XyzStarts, WithScan):
    """A specified grid is one which has defined values for the start position,
    grid and box sizes, etc., as opposed to parameters for a plan which will create
    those parameters at some point (e.g. through optical pin detection)."""


class SpecifiedThreeDGridScan(
    GridCommon,
    SpecifiedGrid,
    SplitScan,
    WithOptionalEnergyChange,
):
    """Parameters representing a so-called 3D grid scan, which consists of doing a
    gridscan in X and Y, followed by one in X and Z."""

    grid1_omega_deg: float = Field(default=GridscanParamConstants.OMEGA_1)  # type: ignore
    grid2_omega_deg: float = Field(default=GridscanParamConstants.OMEGA_2)
    x_step_size_um: float = Field(default=GridscanParamConstants.BOX_WIDTH_UM)
    y_step_size_um: float = Field(default=GridscanParamConstants.BOX_WIDTH_UM)
    z_step_size_um: float = Field(default=GridscanParamConstants.BOX_WIDTH_UM)
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
            set_stub_offsets=self._set_stub_offsets,
            dwell_time_ms=self.exposure_time_s * 1000,
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
