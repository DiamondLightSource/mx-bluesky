from functools import cache

from mx_bluesky.common.external_interaction.config_server import MXConfigServer
from mx_bluesky.hyperion.parameters.constants import (
    HyperionFeatureFlags,
    HyperionFeatureFlagSources,
)


@cache
def get_hyperion_config_server():
    return MXConfigServer(
        "test",
        feature_sources=HyperionFeatureFlagSources,
        feature_dc=HyperionFeatureFlags,
    )  # TODO make url default in config server repo?
