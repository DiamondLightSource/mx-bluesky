import json
from abc import ABC
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator
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


class ParameterVersion(Version):
    @classmethod
    def _parse(cls, version):
        if isinstance(version, cls):
            return version
        return cls.parse(version)


class BaseParameters(BaseModel, ABC):
    """Base class for parameter model, instantiate with a beamline-specific parameter version
    to get automatic checks that parameters are up to date"""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="allow",
    )

    def __hash__(self) -> int:
        return self.json().__hash__()

    parameter_model_version: ParameterVersion

    @field_serializer("parameter_model_version")
    def serialize_parameter_version(self, version: ParameterVersion):
        return str(version)

    @field_validator("parameter_model_version", mode="before")
    @classmethod
    def _validate_version(cls, version_str: str):
        version = ParameterVersion.parse(version_str)
        assert (
            version >= ParameterVersion(major=cls.parameter_model_version.major)
        ), f"Parameter version too old! This version of hyperion uses {cls.parameter_model_version}"
        assert (
            version <= ParameterVersion(major=cls.parameter_model_version.major + 1)
        ), f"Parameter version too new! This version of hyperion uses {cls.parameter_model_version}"
        return version

    @classmethod
    def from_json(cls, input: str | None):
        assert input is not None
        return cls(**json.loads(input))
