from unittest.mock import MagicMock, patch

from bluesky.plan_stubs import null
from bluesky.run_engine import RunEngine
from dodal.devices.aithre_lasershaping.goniometer import Goniometer
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.oav.pin_image_recognition import PinTipDetection

from mx_bluesky.beamlines.aithre_lasershaping.pin_tip_centring import (
    aithre_pin_tip_centre,
)


def return_pixel(pixel, *args):
    yield from null()
    return pixel


@patch(
    "mx_bluesky.beamlines.aithre_lasershaping.pin_tip_centring.pin_tip_centre_plan",
    autospec=True,
)
async def test_when_aithre_pin_tip_centre_called_then_expected_plans_called(
    mock_pin_tip_centring_plan,
    aithre_gonio: Goniometer,
    oav: OAV,
    test_config_files: dict[str, str],
    run_engine: RunEngine,
):
    mock_pin_tip_detection = MagicMock(spec=PinTipDetection)
    run_engine(
        aithre_pin_tip_centre(
            oav,
            aithre_gonio,
            mock_pin_tip_detection,
            50,
            test_config_files["oav_config_json"],
        )
    )

    mock_pin_tip_centring_plan.assert_called_once()
