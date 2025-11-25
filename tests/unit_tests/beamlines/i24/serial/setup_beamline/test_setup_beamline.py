from unittest.mock import patch

import pytest
from dodal.devices.i24.aperture import Aperture
from dodal.devices.i24.beam_center import DetectorBeamCenter
from dodal.devices.i24.beamstop import Beamstop
from dodal.devices.i24.dual_backlight import DualBacklight
from dodal.devices.motors import YZStage
from ophyd_async.core import set_mock_value

from mx_bluesky.beamlines.i24.serial.setup_beamline import setup_beamline

from ..conftest import TEST_LUT


@patch("mx_bluesky.beamlines.i24.serial.setup_beamline.setup_beamline.bps.sleep")
async def test_setup_beamline_for_collection_plan(
    _, aperture: Aperture, backlight: DualBacklight, beamstop: Beamstop, run_engine
):
    run_engine(
        setup_beamline.setup_beamline_for_collection_plan(aperture, backlight, beamstop)
    )

    assert await aperture.position.get_value() == "In"
    assert await beamstop.pos_select.get_value() == "Data Collection"
    assert await beamstop.y_rotation.user_setpoint.get_value() == 0

    assert await backlight.backlight_position.pos_level.get_value() == "Out"


async def test_move_detector_stage_to_position_plan(
    detector_stage: YZStage, run_engine
):
    det_dist = 100
    run_engine(
        setup_beamline.move_detector_stage_to_position_plan(detector_stage, det_dist)
    )

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
    eiger_beam_center: DetectorBeamCenter, dummy_params_ex, run_engine
):
    beam_center_pos = setup_beamline.compute_beam_center_position_from_lut(
        TEST_LUT[dummy_params_ex.detector_name],
        dummy_params_ex.detector_distance_mm,  # 100
        dummy_params_ex.detector_size_constants,
    )
    # test_detector_distance = 100
    # test_detector_params = dummy_params_ex.detector_params
    run_engine(
        setup_beamline.set_detector_beam_center_plan(
            eiger_beam_center,
            beam_center_pos,  # test_detector_params, test_detector_distance
        )
    )

    assert await eiger_beam_center.beam_x.get_value() == pytest.approx(1597.06, 1e-2)
    assert await eiger_beam_center.beam_y.get_value() == pytest.approx(1693.33, 1e-2)


@patch("mx_bluesky.beamlines.i24.serial.setup_beamline.setup_beamline.caput")
@patch("mx_bluesky.beamlines.i24.serial.setup_beamline.setup_beamline.caget")
def test_eiger_raises_error_if_quickshot_and_no_args_list(
    fake_caget, fake_caput, run_engine, dcm, detector_stage
):
    with pytest.raises(TypeError):
        run_engine(setup_beamline.eiger("quickshot", None, dcm, detector_stage))


@patch("mx_bluesky.beamlines.i24.serial.setup_beamline.setup_beamline.caput")
@patch("mx_bluesky.beamlines.i24.serial.setup_beamline.setup_beamline.caget")
@patch("mx_bluesky.beamlines.i24.serial.setup_beamline.setup_beamline.bps.sleep")
def test_eiger_quickshot(_, fake_caget, fake_caput, run_engine, dcm, detector_stage):
    run_engine(
        setup_beamline.eiger("quickshot", ["", "", "1", "0.1"], dcm, detector_stage)
    )
    assert fake_caput.call_count == 30


@patch("mx_bluesky.beamlines.i24.serial.setup_beamline.setup_beamline.caput")
@patch("mx_bluesky.beamlines.i24.serial.setup_beamline.setup_beamline.caget")
@patch("mx_bluesky.beamlines.i24.serial.setup_beamline.setup_beamline.bps.sleep")
def test_eiger_triggered(_, fake_caget, fake_caput, run_engine, dcm, detector_stage):
    set_mock_value(detector_stage.z.user_readback, 300)
    set_mock_value(dcm.wavelength_in_a.user_readback, 1)
    run_engine(
        setup_beamline.eiger("triggered", ["", "", "10", "0.1"], dcm, detector_stage)
    )
    assert fake_caget.call_count == 2
    assert fake_caput.call_count == 30
