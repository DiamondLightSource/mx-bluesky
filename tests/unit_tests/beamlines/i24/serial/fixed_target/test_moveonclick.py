from unittest.mock import ANY, MagicMock, call, patch

import bluesky.plan_stubs as bps
import cv2 as cv
import pytest
from dodal.devices.i24.pmac import PMAC
from dodal.devices.oav.oav_detector import OAV
from ophyd_async.core import get_mock_put

from mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_moveonclick import (
    _calculate_zoom_calibrator,
    onMouse,
    update_ui,
)

ZOOMCALIBRATOR = 6


def fake_generator(value):
    yield from bps.null()
    return value


@pytest.mark.parametrize(
    "beam_position, expected_xmove, expected_ymove",
    [
        (
            (15, 10),
            "#1J:-" + str(15 * ZOOMCALIBRATOR),
            "#2J:-" + str(10 * ZOOMCALIBRATOR),
        ),
        (
            (475, 309),
            "#1J:-" + str(475 * ZOOMCALIBRATOR),
            "#2J:-" + str(309 * ZOOMCALIBRATOR),
        ),
        (
            (638, 392),
            "#1J:-" + str(638 * ZOOMCALIBRATOR),
            "#2J:-" + str(392 * ZOOMCALIBRATOR),
        ),
    ],
)
@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_moveonclick._get_beam_centre"
)
@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_moveonclick._calculate_zoom_calibrator"
)
def test_onMouse_gets_beam_position_and_sends_correct_str(
    fake_zoom_calibrator: MagicMock,
    fake_get_beam_pos: MagicMock,
    beam_position: tuple,
    expected_xmove: str,
    expected_ymove: str,
    pmac: PMAC,
    RE,
):
    fake_zoom_calibrator.side_effect = [fake_generator(ZOOMCALIBRATOR)]
    fake_get_beam_pos.side_effect = [beam_position]
    fake_oav: OAV = MagicMock(spec=OAV)
    onMouse(cv.EVENT_LBUTTONUP, 0, 0, "", param=[RE, pmac, fake_oav])
    mock_pmac_str = get_mock_put(pmac.pmac_string)
    mock_pmac_str.assert_has_calls(
        [
            call(expected_xmove, wait=True, timeout=10),
            call(expected_ymove, wait=True, timeout=10),
        ]
    )


@pytest.mark.parametrize(
    "zoom_percentage, expected_calibrator", [(1, 1.517), (20, 1.012), (50, 0.455)]
)
@patch("mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_moveonclick.bps.rd")
def test_calculate_zoom_calibrator(
    fake_read: MagicMock, zoom_percentage: int, expected_calibrator: float, RE
):
    fake_read.side_effect = [fake_generator(zoom_percentage)]
    fake_oav: OAV = MagicMock(spec=OAV)
    res = RE(_calculate_zoom_calibrator(fake_oav)).plan_result  # type: ignore

    assert res == pytest.approx(expected_calibrator, abs=1e-3)


@patch("mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_moveonclick.cv")
@patch(
    "mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_moveonclick._get_beam_centre"
)
def test_update_ui_uses_correct_beam_centre_for_ellipse(fake_beam_pos, fake_cv):
    mock_frame = MagicMock()
    mock_oav = MagicMock()
    fake_beam_pos.side_effect = [(15, 10)]
    update_ui(mock_oav, mock_frame)
    fake_cv.ellipse.assert_called_once()
    fake_cv.ellipse.assert_has_calls(
        [call(ANY, (15, 10), (12, 8), 0.0, 0.0, 360, (0, 255, 255), thickness=2)]
    )