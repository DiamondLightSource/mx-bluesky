from __future__ import annotations

from enum import StrEnum

from pydantic import Field, field_validator

from mx_bluesky.common.parameters.components import BaseParameters, ParameterVersion
from mx_bluesky.hyperion.external_interaction.config_server import FeatureFlags

PARAMETER_VERSION = ParameterVersion.parse("5.1.0")


class HyperionParameters(BaseParameters):
    features: FeatureFlags = Field(default=FeatureFlags())

    @field_validator("parameter_model_version", mode="before")
    @classmethod
    def _validate_version(cls, version_str: str):
        version = ParameterVersion.parse(version_str)
        assert (
            version >= ParameterVersion(major=PARAMETER_VERSION.major)
        ), f"Parameter version too old! This version of mx-bluesky uses {PARAMETER_VERSION}"
        assert (
            version <= ParameterVersion(major=PARAMETER_VERSION.major + 1)
        ), f"Parameter version too new! This version of hyperion uses {PARAMETER_VERSION}"
        return version


class RotationAxis(StrEnum):
    OMEGA = "omega"
    PHI = "phi"
    CHI = "chi"
    KAPPA = "kappa"
