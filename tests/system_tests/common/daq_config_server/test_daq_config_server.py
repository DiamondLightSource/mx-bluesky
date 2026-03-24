import pytest
from daq_config_server import ConfigClient
from daq_config_server.models.feature_settings.hyperion_feature_settings import (
    HyperionFeatureSettings,
)
from dodal.common.beamlines.beamline_parameters import BEAMLINE_PARAMETER_PATHS
from dodal.common.beamlines.beamline_utils import get_config_client

from mx_bluesky.hyperion.external_interaction.config_server import (
    GDA_DOMAIN_PROPERTIES_PATH,
)
from tests.system_tests.conftest import LOCAL_CONFIG_SERVER_URL


@pytest.mark.system_test
def test_can_get_file_from_real_config_server(config_client: ConfigClient):
    filepath = "/dls_sw/i03/software/daq_configuration/testfile.txt"
    result = config_client.get_file_contents(filepath, desired_return_type=str)
    assert result == "this is for system tests"


@pytest.mark.system_test
def test_get_beamline_paramaters_from_real_config_server(
    config_client: ConfigClient,
):
    filepath = BEAMLINE_PARAMETER_PATHS["i03"]
    config_client.get_file_contents(filepath, desired_return_type=dict)


@pytest.mark.system_test
def test_get_domain_proeprties_from_real_config_server(
    config_client: ConfigClient,
):
    filepath = GDA_DOMAIN_PROPERTIES_PATH
    config_client.get_file_contents(
        filepath, desired_return_type=HyperionFeatureSettings
    )


@pytest.mark.system_test
def test_local_config_server_being_used_with_get_config_client():
    assert get_config_client()._url == LOCAL_CONFIG_SERVER_URL
