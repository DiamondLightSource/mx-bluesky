from __future__ import annotations

import os
from abc import abstractmethod
from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path
from typing import Literal, Self, SupportsInt, cast

from dodal.devices.aperturescatterguard import ApertureValue
from dodal.devices.detector import (
    DetectorParams,
    TriggerMode,
)
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
from pydantic_extra_types.semantic_version import SemanticVersion
from scanspec.core import AxesPoints
from semver import Version

from mx_bluesky.common.parameters.constants import (
    TEST_MODE,
    DetectorParamConstants,
    GridscanParamConstants,
)

PARAMETER_VERSION = Version.parse("5.3.0")


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
    METAL_ID = "Metal ID"

    # Aliases for historic hyperion experiment type mapping
    ROTATION = "SAD"
    GRIDSCAN_2D = "mesh"
    GRIDSCAN_3D = "Mesh3D"


class MxBlueskyParameters(BaseModel):
    model_config = ConfigDict(
        extra="allow",
    )

    def __hash__(self) -> int:
        return self.model_dump_json().__hash__()

    parameter_model_version: SemanticVersion

    @field_validator("parameter_model_version")
    @classmethod
    def _validate_version(cls, version: SemanticVersion):
        assert version >= SemanticVersion(major=PARAMETER_VERSION.major), (
            f"Parameter version too old! This version of hyperion uses {PARAMETER_VERSION}"
        )
        assert version <= SemanticVersion(major=PARAMETER_VERSION.major + 1), (
            f"Parameter version too new! This version of hyperion uses {PARAMETER_VERSION}"
        )
        return version


class WithSnapshot(BaseModel):
    """
    Configures how snapshot images are created.
    Attributes:
        snapshot_directory: Path to the directory where snapshot images will be stored
        snapshot_omegas_deg: list of omega values at which snapshots will be taken. For
            gridscans, this attribute is ignored.
        use_grid_snapshots: This may be specified for rotation snapshots to speed up rotation
            execution. If set to True then rotation snapshots are generated from the
            previously captured grid snapshots. Otherwise they are captured using
            freshly captured snapshots during the rotation plan.
    """

    snapshot_directory: Path
    snapshot_omegas_deg: list[float] | None = None
    use_grid_snapshots: bool = False

    @property
    def take_snapshots(self) -> bool:
        return bool(self.snapshot_omegas_deg) or self.use_grid_snapshots

    @model_validator(mode="after")
    def _validate_omegas_with_grid_snapshots(self) -> Self:
        assert not self.use_grid_snapshots or self.snapshot_omegas_deg is None, (
            "snapshot_omegas may not be specified with use_grid_snapshots"
        )
        return self


class WithOptionalEnergyChange(BaseModel):
    demand_energy_ev: float | None = Field(default=None, gt=0)


class WithVisit(BaseModel):
    beamline: str = Field(default="BL03I", pattern=r"BL\d{2}[BIJS]")
    visit: str = Field(min_length=1)
    det_dist_to_beam_converter_path: str = Field(
        default=DetectorParamConstants.BEAM_XY_LUT_PATH
    )
    insertion_prefix: str = "SR03S" if TEST_MODE else "SR03I"
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
    use_roi_mode: bool = Field(default=GridscanParamConstants.USE_ROI)

    @model_validator(mode="before")
    @classmethod
    def validate_directories(cls, values):
        os.makedirs(values["storage_directory"], exist_ok=True)

        values["snapshot_directory"] = values.get(
            "snapshot_directory",
            Path(values["storage_directory"], "snapshots").as_posix(),
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


class WithPandaGridScan(BaseModel):
    """For experiments which use a PandA for constant-motion grid scans"""

    panda_runup_distance_mm: float = Field(
        default=GridscanParamConstants.PANDA_RUN_UP_DISTANCE_MM
    )


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


class MultiXtalSelection(BaseModel):
    name: str


class TopNByMaxCountSelection(MultiXtalSelection):
    name: Literal["TopNByMaxCount"] = "TopNByMaxCount"  #  pyright: ignore [reportIncompatibleVariableOverride]
    n: int


class WithCentreSelection(BaseModel):
    select_centres: TopNByMaxCountSelection = Field(
        discriminator="name", default=TopNByMaxCountSelection(n=1)
    )

    @property
    def selection_params(self) -> MultiXtalSelection:
        """A helper property because pydantic does not allow polymorphism with base classes
        # only type unions"""
        cast1 = cast(MultiXtalSelection, self.select_centres)
        return cast1


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
