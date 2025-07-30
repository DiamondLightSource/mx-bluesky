from functools import cache

from mx_bluesky.common.external_interaction.config_server import MXConfigClient
from mx_bluesky.hyperion.parameters.constants import (
    HyperionFeatureSetting,
    HyperionFeatureSettingources,
)


@cache
def get_hyperion_config_client() -> MXConfigClient[HyperionFeatureSetting]:
    return MXConfigClient(
        feature_sources=HyperionFeatureSettingources,
        feature_dc=HyperionFeatureSetting,
        url="https://daq-config.diamond.ac.uk",
    )
