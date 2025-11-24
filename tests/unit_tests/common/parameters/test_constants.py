from unittest.mock import patch

import pytest

from mx_bluesky.common.parameters.constants import _get_oav_config_json_path


@pytest.mark.parametrize(
    "beamline, test_mode, expected_path",
    [
        ("i03", True, "tests/test_data/test_OAVCentring.json"),
        (
            "i03",
            False,
            "/dls_sw/i03/software/daq_configuration/json/OAVCentring_hyperion.json",
        ),
        ("i04", False, "/dls_sw/i04/software/daq_configuration/json/OAVCentring.json"),
        ("aithre", True, "tests/test_data/test_OAVCentring.json"),
        (
            "aithre",
            False,
            "/dls/science/groups/i23/aithre/daq_configuration/json/OAVCentring_aithre.json",
        ),
    ],
)
def test_get_oav_config_json_path(beamline: str, test_mode: bool, expected_path: str):
    with (
        patch("mx_bluesky.common.parameters.constants.BEAMLINE", new=beamline),
        patch("mx_bluesky.common.parameters.constants.TEST_MODE", new=test_mode),
    ):
        assert _get_oav_config_json_path() == expected_path
