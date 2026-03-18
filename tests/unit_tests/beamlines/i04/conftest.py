from unittest.mock import MagicMock, patch

import pytest

from mx_bluesky.beamlines.i04.callbacks.murko_callback import MurkoCallback


@pytest.fixture
def murko_callback() -> MurkoCallback:
    callback = MurkoCallback("", "")
    callback.redis_client = MagicMock()
    callback.redis_connected = True
    return callback


@pytest.fixture(autouse=True)
def always_use_i04_beamline(monkeypatch):
    monkeypatch.setenv("BEAMLINE", "i04")


@pytest.fixture(autouse=True)
def patch_get_i04_feature_settings():
    fake_path = "tests/test_data/test_domain_properties"
    with patch(
        "mx_bluesky.beamlines.i04.external_interaction.config_server.GDA_DOMAIN_PROPERTIES_PATH",
        str(fake_path),
    ):
        yield
