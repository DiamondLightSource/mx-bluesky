from unittest.mock import patch

import pytest

from mx_bluesky.beamlines.i24.serial.write_nexus import call_nexgen


def test_call_nexgen_fails_for_wrong_experiment_type(dummy_params_ex):
    with pytest.raises(ValueError):
        call_nexgen(None, dummy_params_ex, 0.6, [100, 100], "fixed-target")


@patch("mx_bluesky.beamlines.i24.serial.write_nexus.SSX_LOGGER")
@patch("mx_bluesky.beamlines.i24.serial.write_nexus.caget")
@patch("mx_bluesky.beamlines.i24.serial.write_nexus.pathlib.Path.read_text")
@patch("mx_bluesky.beamlines.i24.serial.write_nexus.pathlib.Path.exists")
def test_call_nexgen_for_extruder(
    fake_path, fake_read_text, fake_caget, fake_log, dummy_params_ex
):
    fake_caget.return_value = 32
    fake_path.return_value = True
    fake_read_text.return_value = ""
    with patch("mx_bluesky.beamlines.i24.serial.write_nexus.requests") as patch_request:
        call_nexgen(None, dummy_params_ex, 0.6, [1000, 1200], "extruder")
        patch_request.post.assert_called_once()
