from unittest.mock import patch

import pytest


@pytest.fixture
def use_classic_eiger():
    with patch("mx_bluesky.hyperion.blueapi.composites.use_fast_cs_eiger", False):
        yield
