from mx_bluesky.hyperion.external_interaction.config_server import (
    get_hyperion_config_server,
)


# This test does passes as of commit
def test_get_feature_flags():
    server = get_hyperion_config_server()
    features = server.get_feature_flags()
    assert not features.USE_PANDA_FOR_GRIDSCAN
