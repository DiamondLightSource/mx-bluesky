from __future__ import annotations

from abc import abstractmethod
from collections.abc import Sequence
from pathlib import Path
from typing import SupportsInt, TypeVar

from dodal.devices.aperturescatterguard import ApertureValue
from dodal.devices.detector import (
    DetectorParams,
    TriggerMode,
)
from pydantic import (
    BaseModel,
    Field,
    model_validator,
)
from scanspec.core import AxesPoints
from semver import Version

from mx_bluesky.common.parameters.components import (
    BaseParameters,
    IspybExperimentType,
    XyzAxis,
)
from mx_bluesky.hyperion.parameters.constants import CONST

T = TypeVar("T")


class ParameterVersion(Version):
    @classmethod
    def _parse(cls, version):
        if isinstance(version, cls):
            return version
        return cls.parse(version)


PARAMETER_VERSION = ParameterVersion.parse("5.1.0")


# TODO probably just delete this class
class HyperionParameters(BaseParameters): ...


class WithSnapshot(BaseModel):
    snapshot_directory: Path
    snapshot_omegas_deg: list[float] | None = None

    @property
    def take_snapshots(self) -> bool:
        return bool(self.snapshot_omegas_deg)


class WithOptionalEnergyChange(BaseModel):
    demand_energy_ev: float | None = Field(default=None, gt=0)


class WithVisit(BaseModel):
    visit: str = Field(min_length=1)
    zocalo_environment: str = Field(default=CONST.ZOCALO_ENV)
    beamline: str = Field(default=CONST.I03.BEAMLINE, pattern=r"BL\d{2}[BIJS]")
    det_dist_to_beam_converter_path: str = Field(
        default=CONST.PARAM.DETECTOR.BEAM_XY_LUT_PATH
    )
    insertion_prefix: str = Field(
        default=CONST.I03.INSERTION_PREFIX, pattern=r"SR\d{2}[BIJS]"
    )
    detector_distance_mm: float | None = Field(default=None, gt=0)


class DiffractionExperiment(
    HyperionParameters, WithSnapshot, WithOptionalEnergyChange, WithVisit
):
    """For all experiments which use beam"""

    file_name: str
    exposure_time_s: float = Field(gt=0)
    comment: str = Field(default="")
    trigger_mode: TriggerMode = Field(default=TriggerMode.FREE_RUN)
    run_number: int | None = Field(default=None, ge=0)
    selected_aperture: ApertureValue | None = Field(default=None)
    transmission_frac: float = Field(default=0.1)
    ispyb_experiment_type: IspybExperimentType
    storage_directory: str

    @model_validator(mode="before")
    @classmethod
    def validate_snapshot_directory(cls, values):
        snapshot_dir = values.get(
            "snapshot_directory", Path(values["storage_directory"], "snapshots")
        )
        values["snapshot_directory"] = (
            snapshot_dir if isinstance(snapshot_dir, Path) else Path(snapshot_dir)
        )
        return values

    @property
    def num_images(self) -> int:
        return 0

    @property
    @abstractmethod
    def detector_params(self) -> DetectorParams: ...


class WithScan(BaseModel):
    """For experiments where the scan is known"""

    @property
    @abstractmethod
    def scan_points(self) -> AxesPoints: ...

    @property
    @abstractmethod
    def num_images(self) -> int: ...


class SplitScan(BaseModel):
    @property
    @abstractmethod
    def scan_indices(self) -> Sequence[SupportsInt]:
        """Should return the first index of each scan (i.e. for each nexus file)"""
        ...


class WithSample(BaseModel):
    sample_id: int
    sample_puck: int | None = None
    sample_pin: int | None = None


class DiffractionExperimentWithSample(DiffractionExperiment, WithSample): ...


class WithOavCentring(BaseModel):
    oav_centring_file: str = Field(default=CONST.I03.OAV_CENTRING_FILE)


class OptionalXyzStarts(BaseModel):
    x_start_um: float | None = None
    y_start_um: float | None = None
    z_start_um: float | None = None


class XyzStarts(BaseModel):
    x_start_um: float
    y_start_um: float
    z_start_um: float

    def _start_for_axis(self, axis: XyzAxis) -> float:
        match axis:
            case XyzAxis.X:
                return self.x_start_um
            case XyzAxis.Y:
                return self.y_start_um
            case XyzAxis.Z:
                return self.z_start_um


class OptionalGonioAngleStarts(BaseModel):
    omega_start_deg: float | None = None
    phi_start_deg: float | None = None
    chi_start_deg: float | None = None
    kappa_start_deg: float | None = None
