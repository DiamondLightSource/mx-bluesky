from daq_config_server.models.feature_settings.hyperion_feature_settings import (
    HyperionFeatureSettings,
)
from dodal.beamlines.i03 import CONFIG_CLIENT, DAQ_CONFIGURATION_PATH

GDA_DOMAIN_PROPERTIES_PATH = DAQ_CONFIGURATION_PATH + "/domain/domain.properties"


def get_hyperion_feature_settings() -> HyperionFeatureSettings:
    return CONFIG_CLIENT.get_file_contents(
        GDA_DOMAIN_PROPERTIES_PATH,
        desired_return_type=HyperionFeatureSettings,
    )
