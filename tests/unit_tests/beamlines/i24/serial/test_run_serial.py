import argparse
from pathlib import Path
from unittest.mock import ANY, patch

from mx_bluesky.beamlines.i24.serial.run_serial import (
    get_location,
    run_extruder,
    run_fixed_target,
)


@patch("mx_bluesky.beamlines.i24.serial.run_serial.environ")
def test_get_location_not_on_beamline(mock_environ):
    mock_environ.get.return_value = None
    loc = get_location()

    assert loc == "dev"


@patch("mx_bluesky.beamlines.i24.serial.run_serial.subprocess")
@patch("mx_bluesky.beamlines.i24.serial.run_serial._get_file_path")
@patch("mx_bluesky.beamlines.i24.serial.run_serial.get_edm_path")
@patch("mx_bluesky.beamlines.i24.serial.run_serial._parse_input")
def test_run_fixed_extruder_in_test_mode(
    fake_parser, fake_edm_path, fake_filepath, mock_subprocess
):
    fake_parser.return_value = argparse.Namespace(test=True)
    fake_edm_path.return_value = Path("tmp/edm_serial")
    fake_filepath.return_value = Path("test/")

    run_extruder()

    mock_subprocess.run.assert_called_once_with(
        ["bash", Path("test/run_extruder.sh"), "tmp/edm_serial", "--test"]
    )


@patch("mx_bluesky.beamlines.i24.serial.run_serial.subprocess")
@patch("mx_bluesky.beamlines.i24.serial.run_serial.get_edm_path")
@patch("mx_bluesky.beamlines.i24.serial.run_serial._parse_input")
def test_run_fixed_target(fake_parser, fake_edm_path, mock_subprocess):
    fake_parser.return_value = argparse.Namespace(test=False)
    fake_edm_path.return_value = Path("tmp/edm_serial")

    run_fixed_target()

    mock_subprocess.run.assert_called_once_with(["bash", ANY, "tmp/edm_serial", ""])
