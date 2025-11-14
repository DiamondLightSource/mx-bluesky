from functools import cache

from mx_bluesky.common.external_interaction.config_server import MXConfigClient
from mx_bluesky.hyperion.parameters.constants import (
    HyperionFeatureSettings,
    HyperionFeatureSettingsSources,
)


@cache
def get_hyperion_config_client() -> MXConfigClient[HyperionFeatureSettings]:
    return MXConfigClient(
        feature_sources=HyperionFeatureSettingsSources,
        feature_dc=HyperionFeatureSettings,
        url="https://daq-config.diamond.ac.uk",
    )
