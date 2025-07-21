from mx_bluesky.common.external_interaction.config_server import MXConfigServer
from mx_bluesky.hyperion.parameters.constants import (
    HyperionFeatureFlags,
    HyperionFeatureFlagSources,
)


def get_hyperion_config_server():
    return MXConfigServer(
        feature_sources=HyperionFeatureFlagSources,
        feature_dc=HyperionFeatureFlags,
        url="https://daq-config.diamond.ac.uk",
    )
