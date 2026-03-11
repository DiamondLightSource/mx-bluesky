from daq_config_server.models import I04FeatureSettings
from dodal.beamlines.i04 import DAQ_CONFIGURATION_PATH
from dodal.common.beamlines.config_client import get_config_client

GDA_DOMAIN_PROPERTIES_PATH = DAQ_CONFIGURATION_PATH + "/domain/domain.properties"


def get_i04_feature_settings() -> I04FeatureSettings:
    config_client = get_config_client("i04")
    return config_client.get_file_contents(
        GDA_DOMAIN_PROPERTIES_PATH,
        desired_return_type=I04FeatureSettings,
        reset_cached_result=True,
    )
