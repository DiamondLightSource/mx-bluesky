from __future__ import annotations

import json
from abc import abstractmethod
from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path
from typing import SupportsInt, TypeVar

from dodal.devices.aperturescatterguard import ApertureValue
from dodal.devices.detector import (
    DetectorParams,
    TriggerMode,
)
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)
from scanspec.core import AxesPoints
from semver import Version

from mx_bluesky.hyperion.external_interaction.config_server import FeatureFlags
from mx_bluesky.hyperion.parameters.constants import CONST

T = TypeVar("T")


class ParameterVersion(Version):
    @classmethod
    def _parse(cls, version):
        if isinstance(version, cls):
            return version
        return cls.parse(version)


PARAMETER_VERSION = ParameterVersion.parse("5.1.0")


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


class HyperionParameters(BaseModel):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="allow",
    )

    def __hash__(self) -> int:
        return self.json().__hash__()

    features: FeatureFlags = Field(default=FeatureFlags())
    parameter_model_version: ParameterVersion

    @field_serializer("parameter_model_version")
    def serialize_parameter_version(self, version: ParameterVersion):
        return str(version)

    @field_validator("parameter_model_version", mode="before")
    @classmethod
    def _validate_version(cls, version_str: str):
        version = ParameterVersion.parse(version_str)
        assert (
            version >= ParameterVersion(major=PARAMETER_VERSION.major)
        ), f"Parameter version too old! This version of hyperion uses {PARAMETER_VERSION}"
        assert (
            version <= ParameterVersion(major=PARAMETER_VERSION.major + 1)
        ), f"Parameter version too new! This version of hyperion uses {PARAMETER_VERSION}"
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
