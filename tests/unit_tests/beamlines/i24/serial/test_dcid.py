from unittest.mock import patch

from dodal.devices.i24.beam_center import DetectorBeamCenter
from dodal.devices.i24.dcm import DCM
from dodal.devices.i24.focus_mirrors import FocusMirrorsMode
from ophyd_async.testing import set_mock_value

from mx_bluesky.beamlines.i24.serial.dcid import (
    DCID,
    get_resolution,
    read_beam_info_from_hardware,
)
from mx_bluesky.beamlines.i24.serial.parameters import (
    BeamSettings,
    ExtruderParameters,
)
from mx_bluesky.beamlines.i24.serial.setup_beamline import Eiger, Pilatus


def test_read_beam_info_from_hardware(
    dcm: DCM, mirrors: FocusMirrorsMode, eiger_beam_center: DetectorBeamCenter, RE
):
    set_mock_value(dcm.wavelength_in_a, 0.6)
    expected_beam_x = 1605 * 0.075
    expected_beam_y = 1702 * 0.075

    res = RE(
        read_beam_info_from_hardware(dcm, mirrors, eiger_beam_center, "eiger")
    ).plan_result  # type: ignore

    assert res.wavelength_in_a == 0.6
    assert res.beam_size_in_um == (7, 7)
    assert res.beam_center_in_mm == (expected_beam_x, expected_beam_y)


def test_get_resolution():
    distance = 100
    wavelength = 0.649

    eiger_resolution = get_resolution(Eiger(), distance, wavelength)
    pilatus_resolution = get_resolution(Pilatus(), distance, wavelength)

    assert eiger_resolution == 0.78
    assert pilatus_resolution == 0.61


@patch("mx_bluesky.beamlines.i24.serial.dcid.get_resolution")
@patch("mx_bluesky.beamlines.i24.serial.dcid.SSX_LOGGER")
@patch("mx_bluesky.beamlines.i24.serial.dcid.json")
def test_generate_dcid_for_eiger(
    fake_json, fake_log, patch_resolution, dummy_params_ex, RE
):
    test_dcid = DCID(
        server="fake_server",
        emit_errors=False,
        expt_params=dummy_params_ex,
    )

    assert isinstance(test_dcid.detector, Eiger)
    assert isinstance(test_dcid.parameters, ExtruderParameters)

    beam_settings = BeamSettings(
        wavelength_in_a=0.6, beam_size_in_um=(7, 7), beam_center_in_mm=(100, 100)
    )

    with (
        patch("mx_bluesky.beamlines.i24.serial.dcid.requests") as patch_request,
        patch("mx_bluesky.beamlines.i24.serial.dcid.get_auth_header") as fake_auth,
    ):
        test_dcid.generate_dcid(beam_settings, "", "protein.nxs", 10)
        patch_resolution.assert_called_once_with(
            test_dcid.detector,
            dummy_params_ex.detector_distance_mm,
            beam_settings.wavelength_in_a,
        )
        fake_auth.assert_called_once()
        fake_json.dumps.assert_called_once()
        patch_request.post.assert_called_once()


@patch("mx_bluesky.beamlines.i24.serial.dcid.get_resolution")
@patch("mx_bluesky.beamlines.i24.serial.dcid.SSX_LOGGER")
@patch("mx_bluesky.beamlines.i24.serial.dcid.json")
def test_generate_dcid_for_pilatus_with_pump_probe(
    fake_json, fake_log, patch_resolution, dummy_params_ex, RE
):
    dummy_params_ex.detector_name = "pilatus"
    dummy_params_ex.pump_status = True
    dummy_params_ex.laser_dwell_s = 0.01
    dummy_params_ex.laser_delay_s = 0.02

    test_dcid = DCID(
        server="fake_server",
        emit_errors=False,
        expt_params=dummy_params_ex,
    )

    assert isinstance(test_dcid.detector, Pilatus)

    beam_settings = BeamSettings(
        wavelength_in_a=0.6, beam_size_in_um=(7, 7), beam_center_in_mm=(100, 100)
    )

    with (
        patch("mx_bluesky.beamlines.i24.serial.dcid.requests") as patch_request,
        patch("mx_bluesky.beamlines.i24.serial.dcid.get_auth_header") as fake_auth,
    ):
        test_dcid.generate_dcid(beam_settings, "", "test_00001_#####.cbf", 10)
        patch_resolution.assert_called_once_with(
            test_dcid.detector,
            dummy_params_ex.detector_distance_mm,
            beam_settings.wavelength_in_a,
        )
        fake_auth.assert_called_once()
        fake_json.dumps.assert_called_once()
        patch_request.post.assert_called_once()
