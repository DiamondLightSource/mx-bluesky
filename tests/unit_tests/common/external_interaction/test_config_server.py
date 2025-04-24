from functools import cache

import pytest

from mx_bluesky.common.external_interaction.config_server import FeatureFlags


class MockConfigServer:
    def best_effort_get_all_feature_flags(self):
        return {
            "feature_a": False,
            "feature_b": False,
        }


class FakeFeatureFlags(FeatureFlags):
    @staticmethod
    @cache
    def get_config_server() -> MockConfigServer:  # type: ignore
        return MockConfigServer()

    feature_a: bool = False
    feature_b: bool = False


@pytest.fixture
def fake_feature_flags():
    return FakeFeatureFlags(feature_a=False, feature_b=False)


def test_valid_overridden_features(fake_feature_flags: FakeFeatureFlags):
    assert fake_feature_flags.feature_a is False
    assert fake_feature_flags.feature_b is False


def test_invalid_overridden_features():
    with pytest.raises(ValueError, match="Invalid feature toggle"):
        FakeFeatureFlags(feature_x=True)  # type: ignore
