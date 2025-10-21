from functools import cache

from mx_bluesky.beamlines.i04.parameters.constants import (
    I04FeatureSettings,
    I04FeatureSettingsSources,
)
from mx_bluesky.common.external_interaction.config_server import MXConfigClient


@cache
def get_i04_config_client() -> MXConfigClient[I04FeatureSettings]:
    return MXConfigClient(
        feature_sources=I04FeatureSettingsSources,
        feature_dc=I04FeatureSettings,
    )
