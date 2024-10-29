import json
from abc import abstractmethod
from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path
from typing import SupportsInt

from dodal.devices.aperturescatterguard import ApertureValue
from dodal.devices.detector import (
    DetectorParams,
    TriggerMode,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_extra_types.semantic_version import SemanticVersion
from scanspec.core import AxesPoints
from semver import Version


class RotationAxis(StrEnum):
    OMEGA = "omega"
    PHI = "phi"
    CHI = "chi"
    KAPPA = "kappa"


class XyzAxis(StrEnum):
    X = "sam_x"
    Y = "sam_y"
    Z = "sam_z"


class IspybExperimentType(StrEnum):
    # Enum values from ispyb column data type
    SAD = "SAD"  # at or slightly above the peak
    SAD_INVERSE_BEAM = "SAD - Inverse Beam"
    OSC = "OSC"  # "native" (in the absence of a heavy atom)
    COLLECT_MULTIWEDGE = (
        "Collect - Multiwedge"  # "poorly determined" ~ EDNA complex strategy???
    )
    MAD = "MAD"
    HELICAL = "Helical"
    MULTI_POSITIONAL = "Multi-positional"
    MESH = "Mesh"
    BURN = "Burn"
    MAD_INVERSE_BEAM = "MAD - Inverse Beam"
    CHARACTERIZATION = "Characterization"
    DEHYDRATION = "Dehydration"
    TOMO = "tomo"
    EXPERIMENT = "experiment"
    EM = "EM"
    PDF = "PDF"
    PDF_BRAGG = "PDF+Bragg"
    BRAGG = "Bragg"
    SINGLE_PARTICLE = "single particle"
    SERIAL_FIXED = "Serial Fixed"
    SERIAL_JET = "Serial Jet"
    STANDARD = "Standard"  # Routine structure determination experiment
    TIME_RESOLVED = "Time Resolved"  # Investigate the change of a system over time
    DLS_ANVIL_HP = "Diamond Anvil High Pressure"  # HP sample environment pressure cell
    CUSTOM = "Custom"  # Special or non-standard data collection
    XRF_MAP = "XRF map"
    ENERGY_SCAN = "Energy scan"
    XRF_SPECTRUM = "XRF spectrum"
    XRF_MAP_XAS = "XRF map xas"
    MESH_3D = "Mesh3D"
    SCREENING = "Screening"
    STILL = "Still"
    SSX_CHIP = "SSX-Chip"
    SSX_JET = "SSX-Jet"

    # Aliases for historic hyperion experiment type mapping
    ROTATION = "SAD"
    GRIDSCAN_2D = "mesh"
    GRIDSCAN_3D = "Mesh3D"


class MxBlueskyParameters(BaseModel):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="allow",
    )

    def __hash__(self) -> int:
        return self.model_dump_json().__hash__()

    # Version of the parameter model which, eg GDA or BlueAPI are using
    client_parameter_model_version: SemanticVersion

    # Parameter version expected by mx-bluesky
    server_parameter_model: Version

    @field_validator("client_parameter_model_version")
    @classmethod
    def _validate_version(cls, version: Version):
        assert (
            version >= Version(major=cls.server_parameter_model.major)
        ), f"Parameter version too old! This version of hyperion uses {cls.server_parameter_model}"
        assert (
            version <= Version(major=cls.server_parameter_model.major + 1)
        ), f"Parameter version too new! This version of hyperion uses {cls.server_parameter_model}"
        return version

    @classmethod
    def from_json(cls, input: str | None):
        assert input is not None
        return cls(**json.loads(input))


class WithSnapshot(BaseModel):
    snapshot_directory: Path
    snapshot_omegas_deg: list[float] | None = None

    @property
    def take_snapshots(self) -> bool:
        return bool(self.snapshot_omegas_deg)


class WithOptionalEnergyChange(BaseModel):
    demand_energy_ev: float | None = Field(default=None, gt=0)


# todo make sure hyperion creates this with proper defaults
class WithVisit(BaseModel):
    beamline: str
    visit: str = Field(min_length=1)
    det_dist_to_beam_converter_path: str
    insertion_prefix: str
    detector_distance_mm: float | None = Field(default=None, gt=0)


class DiffractionExperiment(
    MxBlueskyParameters, WithSnapshot, WithOptionalEnergyChange, WithVisit
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
    oav_centring_file: str


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
