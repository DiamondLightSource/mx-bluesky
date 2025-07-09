from mx_bluesky.hyperion.external_interaction.config_server import (
    get_hyperion_config_server,
)
from mx_bluesky.hyperion.parameters.constants import HyperionFeatureFlags


def test_get_feature_flags():
    server = get_hyperion_config_server()
    features = server.get_feature_flags()

    expected_features_dict = {
        "USE_GPU_RESULTS": True,
        "USE_PANDA_FOR_GRIDSCAN": False,
        "SET_STUB_OFFSETS": False,
    }

    expected_features = HyperionFeatureFlags(**expected_features_dict)

    assert features == expected_features
