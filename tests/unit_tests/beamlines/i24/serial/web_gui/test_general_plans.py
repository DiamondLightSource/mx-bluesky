from unittest.mock import ANY, patch

import pytest
from dodal.devices.i24.dual_backlight import BacklightPositions

from mx_bluesky.beamlines.i24.serial.parameters.utils import EmptyMapError
from mx_bluesky.beamlines.i24.serial.setup_beamline import Eiger
from mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans import (
    gui_gonio_move_on_click,
    gui_move_backlight,
    gui_move_detector,
    gui_set_parameters,
    gui_sleep,
    gui_stage_move_on_click,
)

from ..conftest import fake_generator


@patch("mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.bps.sleep")
def test_gui_sleep(fake_sleep, RE):
    RE(gui_sleep(3))

    assert fake_sleep.call_count == 3


@patch("mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.caput")
@patch("mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.SSX_LOGGER")
async def test_gui_move_detector(mock_logger, fake_caput, detector_stage, RE):
    RE(gui_move_detector("eiger", detector_stage))
    fake_caput.assert_called_once_with("ME14E-MO-IOC-01:GP101", "eiger")

    assert await detector_stage.y.user_readback.get_value() == 59.0
    mock_logger.debug.assert_called_once()


@patch("mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.bps.rd")
@patch("mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.bps.mv")
def test_gui_gonio_move_on_click(fake_mv, fake_rd, RE):
    fake_rd.side_effect = [fake_generator(1.25), fake_generator(1.25)]

    with (
        patch("mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.i24.oav"),
        patch("mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.i24.vgonio"),
    ):
        RE(gui_gonio_move_on_click((10, 20)))

    fake_mv.assert_called_with(ANY, 0.0125, ANY, 0.025)


@patch("mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.get_detector_type")
def test_gui_set_parameters_raises_error_for_empty_map(mock_det_type, RE):
    mock_det_type.side_effect = [fake_generator(Eiger())]
    with patch(
        "mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.i24.detector_motion"
    ):
        with pytest.raises(EmptyMapError):
            RE(
                gui_set_parameters(
                    "/path/",
                    "chip",
                    0.01,
                    1300,
                    0.3,
                    1,
                    "Oxford",
                    "Lite",
                    [],
                    False,
                    "Short1",
                    0.01,
                    0.005,
                    0.0,
                )
            )


@patch(
    "mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans._move_on_mouse_click_plan"
)
def test_gui_stage_move_on_click(fake_move_plan, oav, pmac, RE):
    RE(gui_stage_move_on_click((200, 200), oav, pmac))
    fake_move_plan.assert_called_once_with(oav, pmac, (200, 200))


@pytest.mark.parametrize("position", ["In", "Out", "White In"])
@patch("mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.SSX_LOGGER")
async def test_gui_move_backlight(mock_logger, position, backlight, RE):
    RE(gui_move_backlight(position, backlight))

    assert (
        await backlight.backlight_position.pos_level.get_value()
        == BacklightPositions(position)
    )
    mock_logger.debug.assert_called_with(f"Backlight moved to {position}")
