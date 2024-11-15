from unittest.mock import patch

from mx_bluesky.beamlines.i24.serial.dcid import (
    get_beam_center,
    get_beamsize,
    get_pilatus_filename_template_from_pvs,
    get_resolution,
)
from mx_bluesky.beamlines.i24.serial.setup_beamline import Eiger, Pilatus


@patch("mx_bluesky.beamlines.i24.serial.dcid.caget")
def test_beamsize(fake_caget):
    beam_size = get_beamsize()
    assert type(beam_size) is tuple
    assert fake_caget.call_count == 2


@patch("mx_bluesky.beamlines.i24.serial.dcid.caget")
def test_beam_center(fake_caget):
    beam_center = get_beam_center(Eiger())
    assert type(beam_center) is tuple
    assert len(beam_center) == 2
    assert fake_caget.call_count == 2


def test_get_resolution():
    distance = 100
    wavelength = 0.649

    eiger_resolution = get_resolution(Eiger(), distance, wavelength)
    pilatus_resolution = get_resolution(Pilatus(), distance, wavelength)

    assert eiger_resolution == 0.78
    assert pilatus_resolution == 0.61


@patch("mx_bluesky.beamlines.i24.serial.dcid.cagetstring")
@patch("mx_bluesky.beamlines.i24.serial.dcid.caget")
def test_get_pilatus_filename_from_pvs(fake_caget, fake_caget_str):
    fake_caget_str.side_effect = ["test_", "%s%s%05d.cbf"]
    fake_caget.return_value = 2

    expected_template = "test_00002_#####.cbf"
    res = get_pilatus_filename_template_from_pvs()
    assert res == expected_template
