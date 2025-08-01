import json
from unittest.mock import MagicMock, call, patch

import pytest
from pydantic.dataclasses import dataclass

from mx_bluesky.common.external_interaction.config_server import MXConfigClient
from mx_bluesky.common.parameters.constants import (
    GDA_DOMAIN_PROPERTIES_PATH,
    FeatureSetting,
    FeatureSettingources,
    OavConstants,
)
from mx_bluesky.hyperion.external_interaction.config_server import (
    get_hyperion_config_client,
)
from mx_bluesky.hyperion.parameters.constants import HyperionFeatureSetting


def test_verify_feature_parameters():
    class BadHyperionFeatureSettingources(FeatureSettingources):
        USE_GPU_RESULTS = "gda.mx.hyperion.xrc.use_gpu_results"
        USE_ZEBRA_FOR_GRIDSCAN = "gda.mx.hyperion.use_panda_for_gridscans"
        SET_STUB_OFFSETS = "gda.mx.hyperion.do_stub_offsets"

    with pytest.raises(AssertionError):
        MXConfigClient(
            feature_sources=BadHyperionFeatureSettingources,
            feature_dc=HyperionFeatureSetting,
        )


@patch("mx_bluesky.common.external_interaction.config_server.LOGGER.warning")
def test_get_json_config_good_request(mock_log_warn: MagicMock):
    with open(OavConstants.OAV_CONFIG_JSON) as f:
        expected_dict = json.loads(f.read())
    assert expected_dict == get_hyperion_config_client().get_json_config(
        OavConstants.OAV_CONFIG_JSON
    )
    mock_log_warn.assert_not_called()


@patch("mx_bluesky.common.external_interaction.config_server.LOGGER.warning")
def test_get_json_config_on_bad_request(mock_log_warn: MagicMock):
    with open(OavConstants.OAV_CONFIG_JSON) as f:
        expected_dict = json.loads(f.read())
    server = get_hyperion_config_client()
    server.get_file_contents = MagicMock(side_effect=Exception)
    assert expected_dict == server.get_json_config(OavConstants.OAV_CONFIG_JSON)
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
    server = get_hyperion_config_client()
    assert server.get_feature_flags() == HyperionFeatureSetting(
        **expected_features_dict
    )
    mock_log_warn.assert_not_called()


def test_get_feature_flags_cache():
    server = get_hyperion_config_client()
    expected_features_dict = {
        "USE_GPU_RESULTS": False,
        "USE_PANDA_FOR_GRIDSCAN": True,
        "SET_STUB_OFFSETS": False,
    }
    expected_features = HyperionFeatureSetting(**expected_features_dict)
    server._cached_features = expected_features
    with patch(
        "mx_bluesky.common.external_interaction.config_server.MXConfigClient.get_file_contents"
    ) as mock_get_file_contents:
        assert server.get_feature_flags() == expected_features
        mock_get_file_contents.assert_not_called()
        server._get_feature_flags(reset_cached_result=True)
        mock_get_file_contents.assert_called_once()


def test_get_json_config_cache():
    server = get_hyperion_config_client()
    with open(OavConstants.OAV_CONFIG_JSON) as f:
        expected_dict = json.loads(f.read())
    get_hyperion_config_client().get_json_config(OavConstants.OAV_CONFIG_JSON)
    assert server._cached_json_config[OavConstants.OAV_CONFIG_JSON] == expected_dict
    with patch(
        "mx_bluesky.common.external_interaction.config_server.MXConfigClient.get_file_contents"
    ) as mock_get_file_contents:
        server.get_json_config(OavConstants.OAV_CONFIG_JSON)
        mock_get_file_contents.assert_not_called()
        server._get_json_config(OavConstants.OAV_CONFIG_JSON, reset_cached_result=True)
        mock_get_file_contents.assert_called_once()


@patch(
    "mx_bluesky.common.external_interaction.config_server.GDA_DOMAIN_PROPERTIES_PATH",
    new="BAD_PATH",
)
@patch("mx_bluesky.common.external_interaction.config_server.LOGGER.warning")
def test_get_feature_flags_bad_request(mock_log_warn: MagicMock):
    server = get_hyperion_config_client()
    assert server.get_feature_flags() == HyperionFeatureSetting()
    mock_log_warn.assert_called_once()


def test_refresh_cache():
    server = get_hyperion_config_client()
    server.get_file_contents = MagicMock()
    server.refresh_cache()
    call_list = [
        call(GDA_DOMAIN_PROPERTIES_PATH, reset_cached_result=True),
        call(OavConstants.OAV_CONFIG_JSON, dict, reset_cached_result=True),
    ]
    server.get_file_contents.assert_has_calls(call_list, any_order=True)


class BadFeatureSettingSources(FeatureSettingources):
    USE_GPU_RESULTS = "gda.mx.hyperion.xrc.use_gpu_results"
    USE_PANDA_FOR_GRIDSCAN = "gda.mx.hyperion.use_panda_for_gridscans"
    SET_STUB_OFFSETS = "gda.mx.hyperion.do_stub_offsets"
    PANDA_RUNUP_DISTANCE_MM = "gda.mx.hyperion.panda_runup_distance_mm"
    MISSING_FEATURE = "gda.mx.hyperion.missing_feature"


@dataclass
class BadFeatureSetting(FeatureSetting):
    USE_GPU_RESULTS: bool = True
    USE_PANDA_FOR_GRIDSCAN: bool = False
    SET_STUB_OFFSETS: bool = False
    MISSING_FEATURE: bool = False
    PANDA_RUNUP_DISTANCE_MM: float = 0.16


@patch("mx_bluesky.common.external_interaction.config_server.LOGGER.warning")
def test_warning_on_missing_features_in_file(mock_log_warn: MagicMock):
    server = MXConfigClient(BadFeatureSettingSources, BadFeatureSetting)

    expected_features_dict = {
        "USE_GPU_RESULTS": True,
        "USE_PANDA_FOR_GRIDSCAN": False,
        "SET_STUB_OFFSETS": False,
        "PANDA_RUNUP_DISTANCE_MM": 0.16,
        "MISSING_FEATURE": False,
    }
    assert server.get_feature_flags() == BadFeatureSetting(**expected_features_dict)
    assert (
        "MISSING_FEATURE" in mock_log_warn.call_args_list[0][0][0]
    )  # call -> tuple -> contents
    mock_log_warn.assert_called_once()
