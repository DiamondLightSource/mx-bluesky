from __future__ import annotations

from typing import TypeVar

from pydantic import (
    Field,
)
from semver import Version

from mx_bluesky.common.parameters.components import MxBlueskyParameters
from mx_bluesky.hyperion.external_interaction.config_server import FeatureFlags

T = TypeVar("T")


PARAMETER_VERSION = Version.parse("5.1.0")


class HyperionParameters(MxBlueskyParameters):
    features: FeatureFlags = Field(default=FeatureFlags())
    server_parameter_model: Version = PARAMETER_VERSION
