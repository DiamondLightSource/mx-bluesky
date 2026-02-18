from __future__ import annotations

from abc import abstractmethod
from typing import Annotated, Generic, TypeVar

from dodal.devices.aperturescatterguard import ApertureValue
from dodal.devices.detector.det_dim_constants import EIGER2_X_4M_SIZE, EIGER2_X_16M_SIZE
from dodal.devices.detector.detector import DetectorParams
from dodal.devices.fast_grid_scan import (
    GridScanParamsCommon,
    ZebraGridScanParamsThreeD,
)
from dodal.utils import get_beamline_name
from pydantic import Field, PrivateAttr, model_validator
from scanspec.core import AxesPoints
from scanspec.core import Path as ScanPath
from scanspec.specs import Concat, Line, Product, Static

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
    "i02-1": EIGER2_X_4M_SIZE,
    "dev": EIGER2_X_16M_SIZE,
    "i03": EIGER2_X_16M_SIZE,
    "i04": EIGER2_X_16M_SIZE,
}

GridScanParamType = TypeVar(
    "GridScanParamType", bound=GridScanParamsCommon, covariant=True
)


class GenericGrid(
    DiffractionExperimentWithSample,
    OptionalGonioAngleStarts,
):
    """
    Parameters used in every MX diffraction experiment using grids. This model should
    be used by plans which have no knowledge of the grid specifications - i.e before
    automatic grid detection has completed.

    Params in GenericGrid currently must be the same for each grid in the gridscan.
    """

    box_size_um: float = Field(default=GridscanParamConstants.BOX_WIDTH_UM)
    grid_width_um: float = Field(default=GridscanParamConstants.WIDTH_UM)
    exposure_time_s: float = Field(default=GridscanParamConstants.EXPOSURE_TIME_S)

    ispyb_experiment_type: IspybExperimentType = Field(
        default=IspybExperimentType.GRIDSCAN_3D
    )
    selected_aperture: ApertureValue | None = Field(default=ApertureValue.SMALL)

    tip_offset_um: float = Field(default=HardwareConstants.TIP_OFFSET_UM)

    # Available after grid detection, used by entry point plans which need to
    # get the grid parameters to retrieve zocalo results
    # Can remove this after https://github.com/DiamondLightSource/python-dlstbx/issues/255 is done
    _specified_grids_params: SpecifiedGrids | None = PrivateAttr(default=None)

    def set_specified_grid_params(self, params: SpecifiedGrids):
        self._specified_grid_params = params

    @property
    def specified_grid_params(self) -> SpecifiedGrids | None:
        return self._specified_grid_params

    # We currently only arm the detector once, regardless of total grids. Detector params
    # must be the same for each grid
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
            omega_start=0,  # Metadata we set on detector isn't currently accurate, but also not used downstream
            omega_increment=0,
            num_images_per_trigger=1,
            num_triggers=self.num_images,
            use_roi_mode=self.use_roi_mode,
            det_dist_to_beam_converter_path=self.det_dist_to_beam_converter_path,
            trigger_mode=self.trigger_mode,
            **optional_args,
        )


PositiveInt = Annotated[int, Field(gt=0)]
PositiveFloat = Annotated[float, Field(gt=0)]


class SpecifiedGrids(GenericGrid, XyzStarts, WithScan, Generic[GridScanParamType]):
    """A specified grid is one which has defined values for the start position,
    grid and box sizes, etc., as opposed to parameters for a plan which will create
    those parameters at some point (e.g. through optical pin detection)."""

    # See https://github.com/DiamondLightSource/mx-bluesky/issues/1634 for a better structure for this
    # class

    omega_starts_deg: list[float] = Field(
        default=[GridscanParamConstants.OMEGA_1, GridscanParamConstants.OMEGA_2]
    )
    x_step_size_um: PositiveFloat = Field(
        default=GridscanParamConstants.BOX_WIDTH_UM
    )  # See https://github.com/DiamondLightSource/mx-bluesky/issues/1632 for this not being a list

    # In a 3D grid scan, y_steps[0] and y_steps[1] refers to Y and Z respectively.
    # We do an omega rotation between scanning across N dimensions to make N different axes
    y_step_sizes_um: list[PositiveFloat] = Field(
        default=[GridscanParamConstants.BOX_WIDTH_UM] * 2
    )
    x_steps: PositiveInt  # See https://github.com/DiamondLightSource/mx-bluesky/issues/1632 for this not being a list
    y_steps: list[PositiveInt]
    _set_stub_offsets: bool = PrivateAttr(default_factory=lambda: False)

    @model_validator(mode="after")
    def _check_lengths_are_same(self):
        fields = {
            "omega_starts_deg": self.omega_starts_deg,
            "y_step_sizes_um": self.y_step_sizes_um,
            "y_steps": self.y_steps,
            "y_starts_um": self.y_starts_um,
            "z_starts_um": self.z_starts_um,
        }

        name_and_length = {name: len(value) for name, value in fields.items()}
        lengths = name_and_length.values()
        if len(set(lengths)) != 1:
            details = "\n".join(
                f"  {name}: length={len(value)}, value={value}"
                for name, value in fields.items()
            )

            raise ValueError("Fields must all have the same length:\n" + details)

        return self

    @property
    @abstractmethod
    def fast_gridscan_params(self) -> GridScanParamType: ...

    def do_set_stub_offsets(self, value: bool):
        self._set_stub_offsets = value

    @property
    def num_grids(self):
        return len(self.y_steps)

    def __len__(self) -> int:
        return self.num_grids

    @property
    def grid_specs(self) -> list[Product[str]]:
        _grid_specs = []
        for idx in range(self.num_grids):
            x_end = self.x_start_um + self.x_step_size_um * (self.x_steps - 1)
            y_end = self.y_starts_um[idx] + self.y_step_sizes_um[idx] * (
                self.y_steps[idx] - 1
            )
            grid_x = Line("sam_x", self.x_start_um, x_end, self.x_steps)
            grid_y = Line("sam_y", self.y_starts_um[idx], y_end, self.y_steps[idx])
            grid_z = Static("sam_z", self.z_starts_um[idx])
            _grid_specs.append(grid_y.zip(grid_z) * ~grid_x)
        return _grid_specs

    @property
    def scan_indices(self) -> list[int]:
        """The first index of each gridscan, useful for writing nexus files/VDS"""
        _scan_indices = [0]
        for idx in range(self.num_grids - 1):
            _scan_indices.append(
                len(
                    ScanPath(self.grid_specs[idx].calculate())
                    .consume()
                    .midpoints["sam_x"]
                )
            )
        return _scan_indices

    @property
    def scan_spec(self) -> Product[str] | Concat[str]:
        """A fully specified ScanSpec object representing all grids, with x, y, z and
        omega positions."""

        _scan_spec = self.grid_specs[0]

        for idx in range(1, self.num_grids - 1):
            _scan_spec = _scan_spec.concat(
                self.grid_specs[idx].concat(self.grid_specs[idx + 1])
            )
        return _scan_spec

    @property
    def scan_points(self) -> list[AxesPoints[str]]:
        """A list of all the points in the scan_spec for each grid."""
        _scan_points = []
        for grid in range(self.num_grids):
            _scan_points.append(
                ScanPath(self.grid_specs[grid].calculate()).consume().midpoints
            )
        return _scan_points

    @property
    def num_images(self) -> int:
        """Total num images in entire scan"""
        _num_images = 0
        for grid in range(len(self.scan_points)):
            _num_images += len(self.scan_points[grid]["sam_x"])
        return _num_images


class SpecifiedThreeDGridScan(
    SpecifiedGrids[ZebraGridScanParamsThreeD],
    SplitScan,
    WithOptionalEnergyChange,
):
    """Parameters representing a so-called 3D grid scan, which consists of doing a
    gridscan in X and Y, followed by one in X and Z."""

    @model_validator(mode="after")
    def validate_y_and_z_axes(self):
        _err_str = "must be length 2 for 3D scans"
        if len(self.y_steps) != 2:
            raise ValueError(f"{self.y_steps=} {_err_str}")
        if len(self.y_step_sizes_um) != 2:
            raise ValueError(f"{self.y_step_sizes_um=} {_err_str}")
        return self

    @property
    def fast_gridscan_params(self) -> ZebraGridScanParamsThreeD:
        return ZebraGridScanParamsThreeD(
            x_steps=self.x_steps,
            y_steps=self.y_steps[0],
            z_steps=self.y_steps[1],
            x_step_size_mm=self.x_step_size_um / 1000,
            y_step_size_mm=self.y_step_sizes_um[0] / 1000,
            z_step_size_mm=self.y_step_sizes_um[1] / 1000,
            x_start_mm=self.x_start_um / 1000,
            y1_start_mm=self.y_starts_um[0] / 1000,
            z1_start_mm=self.z_starts_um[0] / 1000,
            y2_start_mm=self.y_starts_um[1] / 1000,
            z2_start_mm=self.z_starts_um[1] / 1000,
            set_stub_offsets=self._set_stub_offsets,
            dwell_time_ms=self.exposure_time_s * 1000,
            transmission_fraction=self.transmission_frac,
        )
