from daq_config_server.models.feature_settings.hyperion_feature_settings import (
    HyperionFeatureSettings,
)
from dodal.beamlines.i03 import DAQ_CONFIGURATION_PATH
from dodal.common.beamlines.config_client import get_config_client

GDA_DOMAIN_PROPERTIES_PATH = DAQ_CONFIGURATION_PATH + "/domain/domain.properties"


def get_hyperion_feature_settings() -> HyperionFeatureSettings:
    config_client = get_config_client("i03")
    return config_client.get_file_contents(
        GDA_DOMAIN_PROPERTIES_PATH,
        desired_return_type=HyperionFeatureSettings,
    )
