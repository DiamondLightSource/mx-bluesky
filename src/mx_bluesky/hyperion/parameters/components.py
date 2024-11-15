from pydantic import BaseModel, Field

from mx_bluesky.hyperion.external_interaction.config_server import HyperionFeatureFlags


class WithHyperionFeatures(BaseModel):
    features: HyperionFeatureFlags = Field(default=HyperionFeatureFlags())
