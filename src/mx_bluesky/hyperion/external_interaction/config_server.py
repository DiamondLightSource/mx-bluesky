from functools import cache

from mx_bluesky.common.external_interaction.config_server import MXConfigClient
from mx_bluesky.hyperion.parameters.constants import (
    HyperionFeatureSetting,
    HyperionFeatureSettingSources,
)


@cache
def get_hyperion_config_client() -> MXConfigClient[HyperionFeatureSetting]:
    return MXConfigClient(
        feature_sources=HyperionFeatureSettingSources,
        feature_dc=HyperionFeatureSetting,
        url="https://daq-config.diamond.ac.uk",
    )
