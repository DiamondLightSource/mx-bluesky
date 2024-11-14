from __future__ import annotations

from pydantic import (
    BaseModel,
    Field,
)

from mx_bluesky.hyperion.external_interaction.config_server import FeatureFlags


class WithFeatures(BaseModel):
    features: FeatureFlags = Field(default=FeatureFlags())
