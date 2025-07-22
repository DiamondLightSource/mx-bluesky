from mx_bluesky.common.external_interaction.config_server import MXConfigServer
from mx_bluesky.hyperion.external_interaction.config_server import (
    get_hyperion_config_server,
)
from mx_bluesky.hyperion.parameters.constants import HyperionFeatureFlags

class WithHyperionConfigServer:
    @property
    def config_server(self) -> MXConfigServer[HyperionFeatureFlags]:
        return get_hyperion_config_server()

class Wait(MxBlueskyParameters):
    """Represents an instruction from Agamemnon for Hyperion to wait for a specified time
    Attributes:
        duration_s: duration to wait in seconds
    """

    duration_s: float
