from unittest.mock import patch

import pytest
from dodal.devices.i24.aperture import Aperture
from dodal.devices.i24.beam_center import DetectorBeamCenter
from dodal.devices.i24.beamstop import Beamstop
from dodal.devices.i24.dual_backlight import DualBacklight
from dodal.devices.i24.i24_detector_motion import DetectorMotion

from mx_bluesky.beamlines.i24.serial.setup_beamline import setup_beamline

from ..conftest import TEST_LUT


@patch("mx_bluesky.beamlines.i24.serial.setup_beamline.setup_beamline.bps.sleep")
async def test_setup_beamline_for_collection_plan(
    _, aperture: Aperture, backlight: DualBacklight, beamstop: Beamstop, RE
):
    RE(setup_beamline.setup_beamline_for_collection_plan(aperture, backlight, beamstop))

    assert await aperture.position.get_value() == "In"
    assert await beamstop.pos_select.get_value() == "Data Collection"
    assert await beamstop.y_rotation.user_setpoint.get_value() == 0

    assert await backlight.backlight_position.pos_level.get_value() == "Out"


async def test_move_detector_stage_to_position_plan(detector_stage: DetectorMotion, RE):
    det_dist = 100
    RE(setup_beamline.move_detector_stage_to_position_plan(detector_stage, det_dist))

    assert await detector_stage.z.user_setpoint.get_value() == det_dist


def test_compute_beam_center_position_from_lut(dummy_params_ex):
    lut_path = TEST_LUT[dummy_params_ex.detector_name]

    expected_beam_x = 1597.06
    expected_beam_y = 1693.33

    beam_center_pos = setup_beamline.compute_beam_center_position_from_lut(
        lut_path,
        dummy_params_ex.detector_distance_mm,
        dummy_params_ex.detector_size_constants,
    )
    assert beam_center_pos[0] == pytest.approx(expected_beam_x, 1e-2)
    assert beam_center_pos[1] == pytest.approx(expected_beam_y, 1e-2)


async def test_set_detector_beam_center_plan(
    eiger_beam_center: DetectorBeamCenter, dummy_params_ex, RE
):
    beam_center_pos = setup_beamline.compute_beam_center_position_from_lut(
        TEST_LUT[dummy_params_ex.detector_name],
        dummy_params_ex.detector_distance_mm,  # 100
        dummy_params_ex.detector_size_constants,
    )
    # test_detector_distance = 100
    # test_detector_params = dummy_params_ex.detector_params
    RE(
        setup_beamline.set_detector_beam_center_plan(
            eiger_beam_center,
            beam_center_pos,  # test_detector_params, test_detector_distance
        )
    )

    assert await eiger_beam_center.beam_x.get_value() == pytest.approx(1597.06, 1e-2)
    assert await eiger_beam_center.beam_y.get_value() == pytest.approx(1693.33, 1e-2)


@patch("mx_bluesky.beamlines.i24.serial.setup_beamline.setup_beamline.caput")
@patch("mx_bluesky.beamlines.i24.serial.setup_beamline.setup_beamline.caget")
def test_pilatus_raises_error_if_fastchip_and_no_args_list(fake_caget, fake_caput, RE):
    with pytest.raises(TypeError):
        RE(setup_beamline.pilatus("fastchip", None))


@patch("mx_bluesky.beamlines.i24.serial.setup_beamline.setup_beamline.caput")
@patch("mx_bluesky.beamlines.i24.serial.setup_beamline.setup_beamline.caget")
@patch("mx_bluesky.beamlines.i24.serial.setup_beamline.setup_beamline.bps.sleep")
def test_pilatus_quickshot(_, fake_caget, fake_caput, RE):
    RE(setup_beamline.pilatus("quickshot", ["", "", 1, 0.1]))
    assert fake_caput.call_count == 10
    assert fake_caget.call_count == 2


@patch("mx_bluesky.beamlines.i24.serial.setup_beamline.setup_beamline.caput")
@patch("mx_bluesky.beamlines.i24.serial.setup_beamline.setup_beamline.caget")
@patch("mx_bluesky.beamlines.i24.serial.setup_beamline.setup_beamline.bps.sleep")
def test_pilatus_fastchip(_, fake_caget, fake_caput, RE):
    RE(setup_beamline.pilatus("fastchip", ["", "", 10, 0.1]))
    assert fake_caput.call_count == 13
    assert fake_caget.call_count == 2


@patch("mx_bluesky.beamlines.i24.serial.setup_beamline.setup_beamline.caput")
@patch("mx_bluesky.beamlines.i24.serial.setup_beamline.setup_beamline.caget")
def test_eiger_raises_error_if_quickshot_and_no_args_list(
    fake_caget, fake_caput, RE, dcm
):
    with pytest.raises(TypeError):
        RE(setup_beamline.eiger("quickshot", None, dcm))


@patch("mx_bluesky.beamlines.i24.serial.setup_beamline.setup_beamline.caput")
@patch("mx_bluesky.beamlines.i24.serial.setup_beamline.setup_beamline.caget")
@patch("mx_bluesky.beamlines.i24.serial.setup_beamline.setup_beamline.bps.sleep")
def test_eiger_quickshot(_, fake_caget, fake_caput, RE, dcm):
    RE(setup_beamline.eiger("quickshot", ["", "", "1", "0.1"], dcm))
    assert fake_caput.call_count == 30


@patch("mx_bluesky.beamlines.i24.serial.setup_beamline.setup_beamline.bps.rd")
@patch("mx_bluesky.beamlines.i24.serial.setup_beamline.setup_beamline.caput")
@patch("mx_bluesky.beamlines.i24.serial.setup_beamline.setup_beamline.caget")
@patch("mx_bluesky.beamlines.i24.serial.setup_beamline.setup_beamline.bps.sleep")
def test_eiger_triggered(_, fake_caget, fake_caput, fake_read, RE, dcm):
    RE(setup_beamline.eiger("triggered", ["", "", "10", "0.1"], dcm))
    assert fake_caget.call_count == 3
    assert fake_caput.call_count == 30
    assert fake_read.call_count == 1


@pytest.mark.parametrize(
    "action, expected_caputs, expected_sleeps",
    [
        ("Pin_hand_mount", 11, 0),
        ("Pin_rt_hand_mount", 11, 0),
        ("Pin_data_collection", 12, 2),
        ("Pin_rt_data_collection", 13, 2),
    ],
)
@patch("mx_bluesky.beamlines.i24.serial.setup_beamline.setup_beamline.caput")
@patch("mx_bluesky.beamlines.i24.serial.setup_beamline.setup_beamline.bps.sleep")
def test_mode_change(
    fake_sleep, fake_caput, action, expected_caputs, expected_sleeps, RE
):
    RE(setup_beamline.modechange(action))
    assert fake_caput.call_count == expected_caputs
    assert fake_sleep.call_count == expected_sleeps
