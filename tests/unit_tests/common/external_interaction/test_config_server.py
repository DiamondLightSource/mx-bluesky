import json
from time import time
from unittest.mock import MagicMock, call, patch

import pytest

from mx_bluesky.common.external_interaction.config_server import MXConfigServer
from mx_bluesky.common.parameters.constants import (
    GDA_DOMAIN_PROPERTIES_PATH,
    FeatureFlagSources,
    OavConstants,
)
from mx_bluesky.hyperion.external_interaction.config_server import (
    get_hyperion_config_server,
)
from mx_bluesky.hyperion.parameters.constants import HyperionFeatureFlags


def test_verify_feature_parameters():
    class BadHyperionFeatureFlagSources(FeatureFlagSources):
        USE_GPU_RESULTS = "gda.mx.hyperion.xrc.use_gpu_results"
        USE_ZEBRA_FOR_GRIDSCAN = "gda.mx.hyperion.use_panda_for_gridscans"
        SET_STUB_OFFSETS = "gda.mx.hyperion.do_stub_offsets"

    with pytest.raises(AssertionError):
        MXConfigServer(
            feature_sources=BadHyperionFeatureFlagSources,
            feature_dc=HyperionFeatureFlags,
        )


@patch("mx_bluesky.common.external_interaction.config_server.LOGGER.warning")
def test_get_oav_config_good_request(mock_log_warn: MagicMock):
    with open(OavConstants.OAV_CONFIG_JSON) as f:
        expected_dict = json.loads(f.read())
    assert expected_dict == get_hyperion_config_server().get_oav_config()
    mock_log_warn.assert_not_called()


@patch("mx_bluesky.common.external_interaction.config_server.LOGGER.warning")
def test_get_oav_config_on_bad_request(mock_log_warn: MagicMock):
    with open(OavConstants.OAV_CONFIG_JSON) as f:
        expected_dict = json.loads(f.read())
    server = get_hyperion_config_server()
    server.get_file_contents = MagicMock(side_effect=Exception)
    assert expected_dict == server.get_oav_config()
    mock_log_warn.assert_called_once()


@patch(
    "mx_bluesky.common.external_interaction.config_server.GDA_DOMAIN_PROPERTIES_PATH",
    new="tests/test_data/test_domain_properties_with_no_gpu",
)
@patch("mx_bluesky.common.external_interaction.config_server.LOGGER.warning")
def test_get_feature_flags_good_request(mock_log_warn: MagicMock):
    expected_features_dict = {
        "USE_GPU_RESULTS": False,
        "USE_PANDA_FOR_GRIDSCAN": True,
        "SET_STUB_OFFSETS": False,
    }
    server = get_hyperion_config_server()
    assert server.get_feature_flags() == HyperionFeatureFlags(**expected_features_dict)
    mock_log_warn.assert_not_called()


def test_get_feature_flags_cache():
    server = get_hyperion_config_server()
    expected_features_dict = {
        "USE_GPU_RESULTS": False,
        "USE_PANDA_FOR_GRIDSCAN": True,
        "SET_STUB_OFFSETS": False,
    }
    expected_features = HyperionFeatureFlags(**expected_features_dict)
    server._cached_features = expected_features
    server._time_of_last_feature_get = time()
    assert server.get_feature_flags() == expected_features


@patch(
    "mx_bluesky.common.external_interaction.config_server.FEATURE_FLAG_CACHE_LENGTH",
    new=0,
)
def test_get_feature_flags_time_cache():
    # Make cache time 0s and test that cache isn't used
    server = get_hyperion_config_server()
    features_dict = {
        "USE_GPU_RESULTS": False,
        "USE_PANDA_FOR_GRIDSCAN": True,
        "SET_STUB_OFFSETS": False,
    }
    server._cached_features = HyperionFeatureFlags(**features_dict)
    expected_features = HyperionFeatureFlags()
    assert server._cached_features != expected_features
    assert server.get_feature_flags() == expected_features


@patch(
    "mx_bluesky.common.external_interaction.config_server.GDA_DOMAIN_PROPERTIES_PATH",
    new="BAD_PATH",
)
@patch("mx_bluesky.common.external_interaction.config_server.LOGGER.warning")
def test_get_feature_flags_bad_request(mock_log_warn: MagicMock):
    server = get_hyperion_config_server()
    assert server.get_feature_flags() == HyperionFeatureFlags()
    mock_log_warn.assert_called_once()


def test_refresh_cache():
    server = get_hyperion_config_server()
    server.get_file_contents = MagicMock()
    server.refresh_cache()
    call_list = [
        call(GDA_DOMAIN_PROPERTIES_PATH, reset_cached_result=True),
        call(OavConstants.OAV_CONFIG_JSON, dict, reset_cached_result=True),
    ]
    server.get_file_contents.assert_has_calls(call_list, any_order=True)
