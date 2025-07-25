from pydantic import Field

from mx_bluesky.common.parameters.components import (
    MxBlueskyParameters,
    WithPandaGridScan,
)
from mx_bluesky.hyperion.external_interaction.config_server import HyperionFeatureFlags


class WithHyperionUDCFeatures(WithPandaGridScan):
    features: HyperionFeatureFlags = Field(default=HyperionFeatureFlags())


class Wait(MxBlueskyParameters):
    """Represents an instruction from Agamemnon for Hyperion to wait for a specified time
    Attributes:
        duration_s: duration to wait in seconds
    """

    duration_s: float
