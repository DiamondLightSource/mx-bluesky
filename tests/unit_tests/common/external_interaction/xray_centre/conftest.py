from unittest.mock import patch

import pytest

from mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback import (
    GridscanISPyBCallback,
)


@pytest.fixture
def nexus_writer():
    with patch(
        "mx_bluesky.common.external_interaction.callbacks.xray_centre.nexus_callback.NexusWriter"
    ) as nw:
        yield nw


@pytest.fixture
def ispyb_handler():
    return GridscanISPyBCallback()
