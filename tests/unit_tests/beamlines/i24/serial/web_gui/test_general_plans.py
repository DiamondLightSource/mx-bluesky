from unittest.mock import ANY, patch

import bluesky.plan_stubs as bps

from mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans import (
    gui_gonio_move_on_click,
    gui_move_detector,
    gui_sleep,
)


@patch("mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.bps.sleep")
def test_gui_sleep(fake_sleep, RE):
    RE(gui_sleep(3))

    assert fake_sleep.call_count == 3


@patch("mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.caput")
@patch(
    "mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans._move_detector_stage"
)
def test_gui_move_detector(fake_move_plan, fake_caput, RE):
    with patch(
        "mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.i24.detector_motion"
    ):
        RE(gui_move_detector("eiger"))
        fake_move_plan.assert_called_once_with(ANY, -22.0)
    fake_caput.assert_called_once_with("ME14E-MO-IOC-01:GP101", "eiger")


@patch("mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.bps.rd")
@patch("mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.bps.mv")
def test_gui_gonio_move_on_click(fake_mv, fake_rd, RE):
    def fake_generator(value):
        yield from bps.null()
        return value

    fake_rd.side_effect = [fake_generator(1.25), fake_generator(1.25)]

    with (
        patch("mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.i24.oav"),
        patch("mx_bluesky.beamlines.i24.serial.web_gui_plans.general_plans.i24.vgonio"),
    ):
        RE(gui_gonio_move_on_click((10, 20)))

    fake_mv.assert_called_with(ANY, 0.0125, ANY, 0.025)
