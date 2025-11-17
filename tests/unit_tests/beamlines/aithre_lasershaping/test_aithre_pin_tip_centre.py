from functools import partial
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bluesky.plan_stubs import null
from bluesky.run_engine import RunEngine
from dodal.devices.aithre_lasershaping.goniometer import Goniometer
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.oav.pin_image_recognition import PinTipDetection
from ophyd_async.testing import set_mock_value

from mx_bluesky.beamlines.aithre_lasershaping.pin_tip_centring import (
    aithre_pin_tip_centre,
)


def return_pixel(pixel, *args):
    yield from null()
    return pixel


@pytest.fixture
def mock_pin_tip(pin_tip: PinTipDetection):
    pin_tip._get_tip_and_edge_data = AsyncMock(return_value=pin_tip.INVALID_POSITION)
    return pin_tip


@patch(
    "mx_bluesky.beamlines.aithre_lasershaping.pin_tip_centring.pin_tip_centre_plan",
    autospec=True,
)
async def test_when_aithre_pin_tip_centre_called_then_expected_plans_called(
    mock_pin_tip_centring_plan,
    gonio_with_limits: Goniometer,
    oav: OAV,
    test_config_files: dict[str, str],
    run_engine: RunEngine,
):
    run_engine(
        aithre_pin_tip_centre(
            oav,
            gonio_with_limits,
            mock_pin_tip_detection,
            50,
            test_config_files["oav_config_json"],
        )
    )

    assert mock_pin_tip_centring_plan.assert_called_once()
