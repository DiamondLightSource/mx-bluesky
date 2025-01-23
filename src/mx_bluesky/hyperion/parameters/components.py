from pydantic import Field

from mx_bluesky.common.parameters.components import WithPandaGridScan
from mx_bluesky.hyperion.external_interaction.config_server import HyperionFeatureFlags


class WithHyperionUDCFeatures(WithPandaGridScan):
    features: HyperionFeatureFlags = Field(default=HyperionFeatureFlags())
