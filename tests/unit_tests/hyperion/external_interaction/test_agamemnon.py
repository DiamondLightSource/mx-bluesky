import json
from unittest.mock import MagicMock, patch

import pytest

from mx_bluesky.common.parameters.constants import GridscanParamConstants
from mx_bluesky.hyperion.external_interaction.agamemnon import (
    PinType,
    _get_pin_type_from_agamemnon_parameters,
    _single_pin,
    get_next_instruction,
    get_pin_type_from_agamemnon,
    update_params_from_agamemnon,
)
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect
from tests.conftest import raw_params_from_file


@pytest.mark.parametrize(
    "num_wells, well_width, buffer, expected_width",
    [
        (1, 500, 0, 500),
        (6, 50, 100, 400),
        (2, 800, 50, 1650),
    ],
)
def test_given_various_pin_formats_then_pin_width_as_expected(
    num_wells, well_width, buffer, expected_width
):
    pin = PinType(num_wells, well_width, buffer)
    assert pin.full_width == expected_width


def params_from_loop_type(loop_type: str | None):
    return {"sample": {"loopType": loop_type}}


def test_given_no_loop_type_in_parameteers_then_single_pin_returned():
    assert (
        _get_pin_type_from_agamemnon_parameters(params_from_loop_type(None))
        == _single_pin()
    )


@pytest.mark.parametrize(
    "loop_name, expected_loop",
    [
        ("multipin-6x50", PinType(6, 50)),
        ("multipin-6x25.8", PinType(6, 25.8)),
        ("multipin-9x31", PinType(9, 31)),
    ],
)
def test_given_multipin_loop_type_in_parameteers_then_expected_pin_returned(
    loop_name: str, expected_loop: PinType
):
    assert (
        _get_pin_type_from_agamemnon_parameters(params_from_loop_type(loop_name))
        == expected_loop
    )


@patch("mx_bluesky.hyperion.external_interaction.agamemnon.LOGGER")
def test_given_unrecognised_loop_type_in_parameteers_then_warning_logged_single_pin_returned(
    mock_logger: MagicMock,
):
    assert (
        _get_pin_type_from_agamemnon_parameters(params_from_loop_type("nonesense"))
        == _single_pin()
    )
    mock_logger.warning.assert_called_once()


def configure_mock_agamemnon(mock_requests: MagicMock, loop_type: str | None):
    mock_requests.get.return_value.content = json.dumps(
        {"collect": params_from_loop_type(loop_type)}
    )


@patch("mx_bluesky.hyperion.external_interaction.agamemnon.requests")
def test_when_get_next_instruction_called_then_expected_agamemnon_url_queried(
    mock_requests: MagicMock,
):
    configure_mock_agamemnon(mock_requests, None)
    get_next_instruction("i03")
    mock_requests.get.assert_called_once_with(
        "http://agamemnon.diamond.ac.uk/getnextcollect/i03",
        headers={"Accept": "application/json"},
    )


@patch("mx_bluesky.hyperion.external_interaction.agamemnon.requests")
def test_given_agamemnon_returns_multipin_when_get_next_pin_type_from_agamemnon_called_then_multipin_returned(
    mock_requests: MagicMock,
):
    configure_mock_agamemnon(mock_requests, "multipin-6x50")
    assert get_pin_type_from_agamemnon("i03") == PinType(6, 50)


@pytest.fixture
def load_centre_collect_params():
    json_dict = raw_params_from_file(
        "tests/test_data/parameter_json_files/example_load_centre_collect_params.json"
    )
    return LoadCentreCollect(**json_dict)


@patch("mx_bluesky.hyperion.external_interaction.agamemnon.requests")
def test_given_agamemnon_fails_when_update_parameters_called_then_parameters_unchanged(
    mock_requests: MagicMock, load_centre_collect_params: LoadCentreCollect
):
    mock_requests.get.side_effect = Exception("Bad")
    old_grid_width = load_centre_collect_params.robot_load_then_centre.grid_width_um
    params = update_params_from_agamemnon(load_centre_collect_params)
    assert params.robot_load_then_centre.grid_width_um == old_grid_width


@patch("mx_bluesky.hyperion.external_interaction.agamemnon.requests")
def test_given_agamemnon_gives_single_pin_when_update_parameters_called_then_parameters_changed_to_single_pin(
    mock_requests: MagicMock, load_centre_collect_params: LoadCentreCollect
):
    configure_mock_agamemnon(mock_requests, None)
    load_centre_collect_params.robot_load_then_centre.grid_width_um = 0
    load_centre_collect_params.select_centres.n = 0
    params = update_params_from_agamemnon(load_centre_collect_params)
    assert (
        params.robot_load_then_centre.grid_width_um == GridscanParamConstants.WIDTH_UM
    )
    assert params.select_centres.n == 1


@patch("mx_bluesky.hyperion.external_interaction.agamemnon.requests")
def test_given_agamemnon_gives_multi_pin_when_update_parameters_called_then_parameters_changed_to_multi_pin(
    mock_requests: MagicMock, load_centre_collect_params: LoadCentreCollect
):
    configure_mock_agamemnon(mock_requests, "multipin-6x50")
    params = update_params_from_agamemnon(load_centre_collect_params)
    assert params.robot_load_then_centre.grid_width_um == 300
    assert params.select_centres.n == 6
