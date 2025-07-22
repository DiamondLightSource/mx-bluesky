from pydantic import BaseModel, ConfigDict, Field

from mx_bluesky.common.external_interaction.config_server import MXConfigServer
from mx_bluesky.common.parameters.components import MxBlueskyParameters
from mx_bluesky.hyperion.external_interaction.config_server import (
    get_hyperion_config_server,
)
from mx_bluesky.hyperion.parameters.constants import HyperionFeatureFlags


class WithHyperionConfigServer(BaseModel):
    # MyPy checks for base classes signature compatibility, so make this a BaseModel to stop mypy errors

    model_config = ConfigDict(arbitrary_types_allowed=True)
    config_server: MXConfigServer[HyperionFeatureFlags] = Field(
        default_factory=get_hyperion_config_server, exclude=True
    )


class Wait(MxBlueskyParameters):
    """Represents an instruction from Agamemnon for Hyperion to wait for a specified time
    Attributes:
        duration_s: duration to wait in seconds
    """

    duration_s: float
