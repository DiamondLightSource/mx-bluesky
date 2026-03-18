from daq_config_server.models.feature_settings.i04_feature_settings import (
    I04FeatureSettings,
)
from dodal.beamlines.i04 import CONFIG_CLIENT, DAQ_CONFIGURATION_PATH

GDA_DOMAIN_PROPERTIES_PATH = DAQ_CONFIGURATION_PATH + "/domain/domain.properties"


def get_i04_feature_settings() -> I04FeatureSettings:
    return CONFIG_CLIENT.get_file_contents(
        GDA_DOMAIN_PROPERTIES_PATH,
        desired_return_type=I04FeatureSettings,
        reset_cached_result=True,
    )
