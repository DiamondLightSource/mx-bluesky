from datetime import datetime
from unittest.mock import MagicMock, patch

from mx_bluesky.beamlines.i24.serial.write_nexus import call_nexgen


@patch("mx_bluesky.beamlines.i24.serial.write_nexus.bps.sleep", MagicMock())
@patch("mx_bluesky.beamlines.i24.serial.write_nexus.caget")
@patch("mx_bluesky.beamlines.i24.serial.write_nexus.cagetstring")
@patch("mx_bluesky.beamlines.i24.serial.write_nexus.pathlib.Path.read_text")
@patch("mx_bluesky.beamlines.i24.serial.write_nexus.pathlib.Path.exists")
@patch("mx_bluesky.beamlines.i24.serial.write_nexus.requests")
def test_call_nexgen_for_extruder(
    patch_request,
    fake_path,
    fake_read_text,
    fake_caget_str,
    fake_caget,
    dummy_params_ex,
    RE,
):
    fake_caget_str.return_value = f"{dummy_params_ex.filename}_5001"
    fake_caget.return_value = 32
    fake_path.return_value = True
    fake_read_text.return_value = ""
    fake_start_time = datetime(2000, 1, 1)

    RE(call_nexgen(None, dummy_params_ex, 0.6, (1000, 1200), fake_start_time))
    patch_request.post.assert_called_once()

    nexgen_args = patch_request.post.call_args.kwargs["json"]
    assert nexgen_args["expt_type"] == "extruder"
    assert nexgen_args["start_time"] == fake_start_time.isoformat()


@patch("mx_bluesky.beamlines.i24.serial.write_nexus.bps.sleep", MagicMock())
@patch("mx_bluesky.beamlines.i24.serial.write_nexus.caget")
@patch("mx_bluesky.beamlines.i24.serial.write_nexus.cagetstring")
@patch("mx_bluesky.beamlines.i24.serial.write_nexus.pathlib.Path.read_text")
@patch("mx_bluesky.beamlines.i24.serial.write_nexus.pathlib.Path.exists")
@patch("mx_bluesky.beamlines.i24.serial.write_nexus.requests")
def test_call_nexgen_for_fixed_target(
    patch_request,
    fake_path,
    fake_read_text,
    fake_caget_str,
    fake_caget,
    dummy_params_without_pp,
    RE,
):
    expected_filename = f"{dummy_params_without_pp.filename}_5002"
    fake_caget_str.return_value = expected_filename
    fake_caget.return_value = 32
    fake_path.return_value = True
    fake_read_text.return_value = ""
    fake_start_time = datetime(2000, 1, 1)
    RE(call_nexgen(None, dummy_params_without_pp, 0.6, (1000, 1200), fake_start_time))
    patch_request.post.assert_called_once()

    nexgen_args = patch_request.post.call_args.kwargs["json"]
    assert nexgen_args["expt_type"] == "fixed-target"
    assert nexgen_args["filename"] == expected_filename
    assert nexgen_args["start_time"] == fake_start_time.isoformat()
