from unittest.mock import MagicMock

import pytest

from mx_bluesky.beamlines.i04.callbacks.murko_callback import MurkoCallback


@pytest.fixture
def murko_callback() -> MurkoCallback:
    callback = MurkoCallback("", "")
    callback.redis_client = MagicMock()
    callback.redis_connected = True
    return callback


@pytest.fixture(autouse=True)
def patch_beamline_env_variable(monkeypatch):
    monkeypatch.setenv("BEAMLINE", "i04")
