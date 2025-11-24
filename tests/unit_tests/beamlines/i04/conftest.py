from unittest.mock import MagicMock

import pytest

from mx_bluesky.beamlines.i04.callbacks.murko_callback import MurkoCallback


@pytest.fixture
def murko_callback() -> MurkoCallback:
    callback = MurkoCallback("", "")
    callback.redis_client = MagicMock()
    return callback
