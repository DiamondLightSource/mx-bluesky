from functools import cache

import pytest

from mx_bluesky.common.external_interaction.config_server import FeatureFlags


class MockConfigServer:
    def best_effort_get_all_feature_flags(self):
        return {
            "feature_a": False,
            "feature_b": False,
        }


class TestFeatureFlags(FeatureFlags):
    @staticmethod
    @cache
    def get_config_server() -> MockConfigServer:  # type: ignore
        return MockConfigServer()

    feature_a: bool = False
    feature_b: bool = False


def test_valid_overridden_features():
    flags = TestFeatureFlags(feature_a=True, feature_b=True)
    assert flags.feature_a is True
    assert flags.feature_b is True


def test_invalid_overridden_features():
    with pytest.raises(ValueError, match="Invalid feature toggle"):
        TestFeatureFlags(invalid_feature=True)  # type: ignore
