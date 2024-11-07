from dodal.devices.i24.beam_center import DetectorBeamCenter
from dodal.devices.i24.dcm import DCM
from dodal.devices.i24.focus_mirrors import FocusMirrorsMode
from ophyd_async.core import set_mock_value

from mx_bluesky.beamlines.i24.serial.dcid import (
    get_resolution,
    read_beam_info_from_hardware,
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
