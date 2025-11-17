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
    "mx_bluesky.common.experiment_plans.pin_tip_centring_plan.wait_for_tip_to_be_found",
    new=partial(return_pixel, (200, 200)),
)
@patch(
    "dodal.devices.oav.utils.get_move_required_so_that_beam_is_at_pixel",
    autospec=True,
)
@patch(
    "mx_bluesky.common.experiment_plans.pin_tip_centring_plan.move_pin_into_view",
)
@patch(
    "mx_bluesky.beamlines.aithre_lasershaping.pin_tip_centring.pin_tip_centre_plan",
    autospec=True,
)
@patch(
    "mx_bluesky.common.experiment_plans.pin_tip_centring_plan.bps.sleep",
    autospec=True,
)
async def test_when_aithre_pin_tip_centre_called_then_expected_plans_called(
    mock_sleep,
    mock_pin_tip_centring_plan,
    mock_move_into_view,
    get_move: MagicMock,
    gonio_with_limits: Goniometer,
    oav: OAV,
    test_config_files: dict[str, str],
    run_engine: RunEngine,
):
    set_mock_value(oav.zoom_controller.level, "1.0")
    set_mock_value(gonio_with_limits.omega.user_readback, 0)
    mock_pin_tip_detection = MagicMock(spec=PinTipDetection)
    mock_move_into_view.side_effect = partial(return_pixel, (100, 100))
    run_engine(
        aithre_pin_tip_centre(
            oav,
            gonio_with_limits,
            mock_pin_tip_detection,
            50,
            test_config_files["oav_config_json"],
        )
    )

    assert mock_pin_tip_centring_plan.call_count == 1
