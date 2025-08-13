import json
from collections.abc import Generator
from math import isclose
from pathlib import PosixPath
from unittest.mock import MagicMock, patch

import pytest
from dodal.devices.zebra.zebra import RotationDirection

from mx_bluesky.common.parameters.constants import GridscanParamConstants
from mx_bluesky.hyperion.external_interaction.agamemnon import (
    _get_next_instruction,
    _get_pin_type_from_agamemnon_collect_parameters,
    _get_withenergy_parameters_from_agamemnon,
    _get_withvisit_parameters_from_agamemnon,
    _instruction_and_data,
    _PinType,
    _SinglePin,
    compare_params,
    create_parameters_from_agamemnon,
    update_params_from_agamemnon,
)
from mx_bluesky.hyperion.parameters.components import Wait
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect


@pytest.mark.parametrize(
    "num_wells, well_width, buffer, expected_width",
    [
        (3, 500, 0, 1000),
        (6, 50, 100, 450),
        (2, 800, 50, 900),
    ],
)
def test_given_various_pin_formats_then_pin_width_as_expected(
    num_wells, well_width, buffer, expected_width
):
    pin = _PinType(num_wells, well_width, buffer)
    assert pin.full_width == expected_width


def set_up_agamemnon_params(
    loop_type: str | None = None,
    prefix: str | None = None,
    distance: int | None = None,
    wavelength: float | None = None,
):
    return {
        "collection": [{"distance": distance, "wavelength": wavelength}],
        "prefix": prefix,
        "sample": {"loopType": loop_type, "id": 1, "position": 1, "container": 1},
    }


def test_given_no_loop_type_in_parameters_then_single_pin_returned():
    assert (
        _get_pin_type_from_agamemnon_collect_parameters(set_up_agamemnon_params())
        == _SinglePin()
    )


@pytest.mark.parametrize(
    "loop_name, expected_loop",
    [
        ("multipin_6x50+9", _PinType(6, 50, 9)),
        ("multipin_6x25.8+8.6", _PinType(6, 25.8, 8.6)),
        ("multipin_9x31+90", _PinType(9, 31, 90)),
    ],
)
def test_given_multipin_loop_type_in_parameters_then_expected_pin_returned(
    loop_name: str, expected_loop: _PinType
):
    assert (
        _get_pin_type_from_agamemnon_collect_parameters(
            set_up_agamemnon_params(loop_name)
        )
        == expected_loop
    )


@pytest.mark.parametrize(
    "loop_name",
    [
        "nonesense",
        "single_pin_78x89+1",
    ],
)
@patch("mx_bluesky.hyperion.external_interaction.agamemnon.LOGGER")
def test_given_completely_unrecognised_loop_type_in_parameters_then_warning_logged_single_pin_returned(
    mock_logger: MagicMock,
    loop_name: str,
):
    assert (
        _get_pin_type_from_agamemnon_collect_parameters(
            set_up_agamemnon_params(loop_name)
        )
        == _SinglePin()
    )
    mock_logger.warning.assert_called_once()


@pytest.mark.parametrize(
    "loop_name",
    [
        "multipin_67x56",
        "multipin_90+4",
        "multipin_8",
        "multipin_6x50+",
        "multipin_6x50+98.",
        "multipin_6x50+.1",
        "multipin_6x.50+98",
        "multipin_6x50+98.1.2",
        "multipin_6x50.5.6+98",
        "multipin_6x50+98..1",
        "multipin_6x.50+.98",
        "multipin_6x+98",
    ],
)
def test_given_unrecognised_multipin_in_parameters_then_warning_logged_single_pin_returned(
    loop_name: str,
):
    with pytest.raises(ValueError) as e:
        _get_pin_type_from_agamemnon_collect_parameters(
            set_up_agamemnon_params(loop_name)
        )
    assert "Expected multipin format" in str(e.value)


def configure_mock_agamemnon(mock_requests: MagicMock, loop_type: str | None):
    mock_requests.get.return_value.content = json.dumps(
        {"collect": set_up_agamemnon_params(loop_type, "", 255, 0.9)}
    )


@patch("mx_bluesky.hyperion.external_interaction.agamemnon.requests")
def test_when_get_next_instruction_called_then_expected_agamemnon_url_queried(
    mock_requests: MagicMock,
):
    configure_mock_agamemnon(mock_requests, None)
    _get_next_instruction("i03")
    mock_requests.get.assert_called_once_with(
        "http://agamemnon.diamond.ac.uk/getnextcollect/i03",
        headers={"Accept": "application/json"},
    )


@patch("mx_bluesky.hyperion.external_interaction.agamemnon.requests")
def test_given_agamemnon_returns_an_unexpected_response_then_exception_is_thrown(
    mock_requests: MagicMock,
):
    mock_requests.get.return_value.content = json.dumps({"not_collect": ""})
    with pytest.raises(KeyError) as e:
        create_parameters_from_agamemnon()
    assert "not_collect" in str(e.value)


@patch("mx_bluesky.hyperion.external_interaction.agamemnon.requests")
def test_given_agamemnon_returns_multipin_when_get_next_pin_type_from_agamemnon_called_then_multipin_returned(
    mock_requests: MagicMock,
):
    configure_mock_agamemnon(mock_requests, "multipin_6x50+98.1")
    instruction, params = _instruction_and_data(_get_next_instruction("i03"))
    assert _get_pin_type_from_agamemnon_collect_parameters(params) == _PinType(
        6, 50, 98.1
    )


@patch("mx_bluesky.hyperion.external_interaction.agamemnon.requests")
def test_update_params_from_agamemnon_leaves_parameters_unchanged_when_agamemnon_fails(
    mock_requests: MagicMock, load_centre_collect_params: LoadCentreCollect
):
    mock_requests.get.side_effect = Exception("Bad")
    old_grid_width = load_centre_collect_params.robot_load_then_centre.grid_width_um
    params = update_params_from_agamemnon(load_centre_collect_params)
    assert params.robot_load_then_centre.grid_width_um == old_grid_width


@patch("mx_bluesky.hyperion.external_interaction.agamemnon.compare_params")
@patch("mx_bluesky.hyperion.external_interaction.agamemnon.requests")
def test_update_params_from_agamemnon_changes_params_to_single_pin_when_agamemnon_gives_single_pin(
    mock_requests: MagicMock,
    mock_compare_params: MagicMock,
    load_centre_collect_params: LoadCentreCollect,
):
    configure_mock_agamemnon(mock_requests, None)
    load_centre_collect_params.robot_load_then_centre.grid_width_um = 0
    load_centre_collect_params.select_centres.n = 0
    params = update_params_from_agamemnon(load_centre_collect_params)
    assert (
        params.robot_load_then_centre.grid_width_um == GridscanParamConstants.WIDTH_UM
    )
    assert params.select_centres.n == 1
    assert params.multi_rotation_scan.snapshot_omegas_deg


@patch("mx_bluesky.hyperion.external_interaction.agamemnon.compare_params")
@patch("mx_bluesky.hyperion.external_interaction.agamemnon.requests")
def test_update_params_from_agamemnon_applies_multipin_attribs_given_agamemnon_returns_multipin(
    mock_requests: MagicMock,
    mock_compare_params: MagicMock,
    load_centre_collect_params: LoadCentreCollect,
):
    configure_mock_agamemnon(mock_requests, "multipin_6x50+10")
    params = update_params_from_agamemnon(load_centre_collect_params)
    assert params.robot_load_then_centre.grid_width_um == 270
    assert params.select_centres.n == 6
    assert params.robot_load_then_centre.tip_offset_um == 135
    assert not params.multi_rotation_scan.snapshot_omegas_deg


@patch("mx_bluesky.hyperion.external_interaction.agamemnon.requests")
def test_update_params_from_agamemnon_deduces_correct_url_given_set_of_parameters(
    mock_requests: MagicMock, load_centre_collect_params: LoadCentreCollect
):
    update_params_from_agamemnon(load_centre_collect_params)
    mock_requests.get.assert_called_once_with(
        "http://agamemnon.diamond.ac.uk/getnextcollect/i03",
        headers={"Accept": "application/json"},
    )


@patch("mx_bluesky.hyperion.external_interaction.agamemnon.LOGGER")
@patch("mx_bluesky.hyperion.external_interaction.agamemnon.requests")
def test_update_params_from_agamemnon_logs_warning_when_exception_occurs(
    mock_requests: MagicMock,
    mock_logger: MagicMock,
    load_centre_collect_params: LoadCentreCollect,
):
    configure_mock_agamemnon(mock_requests, "multipin_unknown")

    update_params_from_agamemnon(load_centre_collect_params)

    mock_logger.warning.assert_called_once()
    assert (
        "Failed to update parameters: Agamemnon loop type of multipin_unknown "
        "not recognised" in mock_logger.warning.mock_calls[0].args[0]
    )


@pytest.mark.parametrize(
    "prefix, expected_visit",
    [
        ["/dls/i03/data/2025/mx23694-130/foo/bar", "mx23694-130"],
        ["/dls/not-i03/data/2021/mx84743-230", "mx84743-230"],
    ],
)
def test_given_valid_prefix_then_correct_visit_is_set(prefix: str, expected_visit: str):
    visit, _ = _get_withvisit_parameters_from_agamemnon(
        set_up_agamemnon_params(None, prefix, None)
    )
    assert visit == expected_visit


@pytest.mark.parametrize(
    "prefix",
    [
        "/not-dls/i03/data/2025/mx23694-130/foo/bar",
        "/dls/i03/not-data/2025/mx23694-130/foo/bar",
        "/foo/bar/i03/data/2025/mx23694-130",
    ],
)
def test_given_invalid_prefix_then_exception_raised(prefix: str):
    with pytest.raises(ValueError) as e:
        _get_withvisit_parameters_from_agamemnon(
            set_up_agamemnon_params(None, prefix, None)
        )

    assert "MX-General root structure" in str(e.value)


def test_no_prefix_raises_exception():
    with pytest.raises(KeyError) as e:
        _get_withvisit_parameters_from_agamemnon({"not_collect": ""})

    assert "Unexpected json from agamemnon" in str(e.value)


@pytest.mark.parametrize(
    "mock_error, mock_log",
    [
        (ValueError(), "Failed to compare parameters: "),
        (Exception(), "Unexpected error occurred. Failed to compare parameters: "),
    ],
)
@patch("mx_bluesky.hyperion.external_interaction.agamemnon.requests")
@patch("mx_bluesky.hyperion.external_interaction.agamemnon.LOGGER")
@patch(
    "mx_bluesky.hyperion.external_interaction.agamemnon._populate_parameters_from_agamemnon"
)
def test_compare_params_logs_exception_if_fails_to_populate_parameters_from_hyperion(
    mock_populate_params,
    mock_logger,
    mock_requests,
    mock_error,
    mock_log,
    load_centre_collect_params: LoadCentreCollect,
):
    configure_mock_agamemnon(mock_requests, None)
    mock_populate_params.side_effect = mock_error
    compare_params(
        load_centre_collect_params,
    )
    assert mock_log in mock_logger.mock_calls[0][1][0]


@patch("mx_bluesky.hyperion.external_interaction.agamemnon.LOGGER")
@patch(
    "mx_bluesky.hyperion.external_interaction.agamemnon.create_parameters_from_agamemnon",
    MagicMock(return_value=[]),
)
def test_compare_params_logs_message_if_agamemnon_returns_no_instructions(
    mock_logger: MagicMock, load_centre_collect_params: LoadCentreCollect
):
    compare_params(
        load_centre_collect_params,
    )
    mock_logger.info.assert_called_once_with("Agamemnon returned no instructions")


@pytest.fixture
def agamemnon_response(request) -> Generator[str, None, None]:
    with (
        patch("mx_bluesky.common.parameters.components.os", new=MagicMock()),
        patch(
            "mx_bluesky.hyperion.external_interaction.agamemnon.requests"
        ) as mock_requests,
        open(request.param) as json_file,
    ):
        example_json = json_file.read()
        mock_requests.get.return_value.content = example_json
        yield example_json


@pytest.mark.parametrize(
    "agamemnon_response",
    [
        "tests/test_data/agamemnon/example_native.json",
        "tests/test_data/agamemnon/example_collect_multipin.json",
    ],
    indirect=True,
)
@patch("mx_bluesky.hyperion.external_interaction.agamemnon.LOGGER")
@patch("mx_bluesky.hyperion.parameters.rotation.os", new=MagicMock())
@patch("dodal.devices.detector.detector.Path", new=MagicMock())
@patch("dodal.utils.os", new=MagicMock())
def test_compare_params_causes_no_warning_when_compared_to_gda_params(
    mock_logger: MagicMock,
    agamemnon_response: str,
    load_centre_collect_params: LoadCentreCollect,
):
    compare_params(load_centre_collect_params)
    mock_logger.warning.assert_not_called()


@pytest.mark.parametrize(
    "agamemnon_response",
    ["tests/test_data/agamemnon/example_native.json"],
    indirect=True,
)
def test_create_parameters_from_agamemnon_contains_expected_data(agamemnon_response):
    hyperion_params_list = create_parameters_from_agamemnon()
    for hyperion_params in hyperion_params_list:
        assert isinstance(hyperion_params, LoadCentreCollect)
        assert hyperion_params.visit == "mx34598-77"
        assert isclose(hyperion_params.detector_distance_mm, 237.017, abs_tol=1e-3)  # type: ignore
        assert hyperion_params.sample_id == 6501159
        assert hyperion_params.sample_puck == 5
        assert hyperion_params.sample_pin == 4
        assert str(hyperion_params.parameter_model_version) == "5.3.0"
        assert hyperion_params.select_centres.n == 1


@pytest.mark.parametrize(
    "agamemnon_response",
    ["tests/test_data/agamemnon/example_native.json"],
    indirect=True,
)
def test_create_parameters_from_agamemnon_contains_expected_robot_load_then_centre_data(
    agamemnon_response,
):
    hyperion_params_list = create_parameters_from_agamemnon()
    load_centre_collect_list = [
        p for p in hyperion_params_list if isinstance(p, LoadCentreCollect)
    ]
    assert len(hyperion_params_list) == len(load_centre_collect_list) == 2

    assert load_centre_collect_list[0].robot_load_then_centre.chi_start_deg == 0.0
    assert load_centre_collect_list[1].robot_load_then_centre.chi_start_deg == 30.0
    for robot_load_params in [
        params.robot_load_then_centre for params in load_centre_collect_list
    ]:
        assert robot_load_params.visit == "mx34598-77"
        assert isclose(robot_load_params.detector_distance_mm, 237.017, abs_tol=1e-3)  # type: ignore
        assert robot_load_params.sample_id == 6501159
        assert robot_load_params.sample_puck == 5
        assert robot_load_params.sample_pin == 4
        assert robot_load_params.demand_energy_ev == 12700.045934258673
        assert robot_load_params.omega_start_deg == 0.0
        assert robot_load_params.transmission_frac == 1.0
        assert robot_load_params.tip_offset_um == 300.0
        assert robot_load_params.grid_width_um == 600.0
        assert str(robot_load_params.parameter_model_version) == "5.3.0"
        assert (
            robot_load_params.storage_directory
            == "/dls/i03/data/2025/mx34598-77/auto/CBLBA/CBLBA-x00242/xraycentring"
        )
        assert robot_load_params.file_name == "CBLBA-x00242"
        assert robot_load_params.snapshot_directory == PosixPath(
            "/dls/i03/data/2025/mx34598-77/auto/CBLBA/CBLBA-x00242/xraycentring/snapshots"
        )


@patch("mx_bluesky.hyperion.parameters.rotation.os", new=MagicMock())
@patch("dodal.devices.detector.detector.Path", new=MagicMock())
@pytest.mark.parametrize(
    "agamemnon_response",
    ["tests/test_data/agamemnon/example_native.json"],
    indirect=True,
)
def test_create_parameters_from_agamemnon_contains_expected_rotation_data(
    agamemnon_response,
):
    hyperion_params_list = create_parameters_from_agamemnon()
    assert len(hyperion_params_list) == 2
    for hyperion_params in hyperion_params_list:
        assert isinstance(hyperion_params, LoadCentreCollect)
        rotation_params = hyperion_params.multi_rotation_scan
        assert rotation_params.visit == "mx34598-77"
        assert isclose(rotation_params.detector_distance_mm, 237.017, abs_tol=1e-3)  # type: ignore
        assert rotation_params.detector_params.omega_start == 0.0
        assert rotation_params.detector_params.exposure_time_s == 0.003
        assert rotation_params.detector_params.num_images_per_trigger == 3600
        assert rotation_params.num_images == 3600
        assert rotation_params.transmission_frac == 0.1426315789473684
        assert rotation_params.comment == "Complete_P1_sweep1 "
        assert rotation_params.ispyb_experiment_type == "OSC"

        assert rotation_params.demand_energy_ev == 12700.045934258673
        assert str(rotation_params.parameter_model_version) == "5.3.0"
        assert (
            rotation_params.storage_directory
            == "/dls/i03/data/2025/mx34598-77/auto/CBLBA/CBLBA-x00242"
        )
        assert rotation_params.file_name == "CBLBA-x00242"
        assert rotation_params.snapshot_directory == PosixPath(
            "/dls/i03/data/2025/mx34598-77/auto/CBLBA/CBLBA-x00242/snapshots"
        )

    individual_scans = list(
        hyperion_params_list[0].multi_rotation_scan.single_rotation_scans  # type: ignore
    ) + list(
        hyperion_params_list[1].multi_rotation_scan.single_rotation_scans  # type: ignore
    )
    assert len(individual_scans) == 2
    assert individual_scans[0].scan_points["omega"][1] == 0.1
    assert individual_scans[0].phi_start_deg == 0.0
    assert individual_scans[0].chi_start_deg == 0.0
    assert individual_scans[0].rotation_direction == RotationDirection.POSITIVE
    assert individual_scans[1].scan_points["omega"][1] == 0.1
    assert individual_scans[1].phi_start_deg == 0.0
    assert individual_scans[1].chi_start_deg == 30.0
    assert individual_scans[1].rotation_direction == RotationDirection.POSITIVE


@pytest.mark.parametrize(
    "agamemnon_response",
    ["tests/test_data/agamemnon/example_collect_multipin.json"],
    indirect=True,
)
def test_create_parameters_from_agamemnon_populates_multipin_parameters_from_agamemnon(
    agamemnon_response,
):
    hyperion_params_list = create_parameters_from_agamemnon()
    for hyperion_params in hyperion_params_list:
        assert hyperion_params.select_centres.n == 6  # type: ignore


@pytest.mark.parametrize(
    "agamemnon_response",
    ["tests/test_data/agamemnon/example_native.json"],
    indirect=True,
)
def test_create_parameters_from_agamemnon_creates_multiple_load_centre_collect_for_native_collection(
    agamemnon_response,
):
    hyperion_params_list = create_parameters_from_agamemnon()
    assert len(hyperion_params_list) == 2
    assert (
        sum(
            [
                len(hyperion_params.multi_rotation_scan.rotation_scans)  # type: ignore
                for hyperion_params in hyperion_params_list
            ]
        )
        == 2
    )


@pytest.mark.parametrize(
    "agamemnon_response",
    ["tests/test_data/agamemnon/example_native.json"],
    indirect=True,
)
def test_get_withenergy_parameters_from_agamemnon(agamemnon_response):
    _, agamemnon_params = _instruction_and_data(_get_next_instruction("i03"))
    demand_energy_ev = _get_withenergy_parameters_from_agamemnon(agamemnon_params)
    assert demand_energy_ev["demand_energy_ev"] == 12700.045934258673


def test_get_withenergy_parameters_from_agamemnon_when_no_wavelength():
    agamemnon_params = {}
    demand_energy_ev = _get_withenergy_parameters_from_agamemnon(agamemnon_params)
    assert demand_energy_ev["demand_energy_ev"] is None


@patch("mx_bluesky.hyperion.external_interaction.agamemnon.requests")
def test_create_parameters_from_agamemnon_returns_empty_list_if_collect_instruction_is_empty(
    mock_requests,
):
    mock_requests.get.return_value.content = json.dumps({"collect": {}})
    params = create_parameters_from_agamemnon()
    assert params == []


@patch("mx_bluesky.hyperion.external_interaction.agamemnon.requests")
def test_create_parameters_from_agamemnon_returns_empty_list_if_no_instruction(
    mock_requests,
):
    mock_requests.get.return_value.content = json.dumps({})
    params = create_parameters_from_agamemnon()
    assert params == []


@pytest.mark.parametrize(
    "agamemnon_response",
    ["tests/test_data/agamemnon/example_collect_multipin.json"],
    indirect=True,
)
def test_create_parameters_from_agamemnon_does_not_return_none_if_queue_is_not_empty(
    agamemnon_response,
):
    params = create_parameters_from_agamemnon()
    assert params is not None


@pytest.mark.parametrize(
    "agamemnon_response", ["tests/test_data/agamemnon/example_wait.json"], indirect=True
)
def test_create_parameters_from_agamemnon_creates_wait(agamemnon_response):
    params = create_parameters_from_agamemnon()
    assert len(params) == 1
    assert isinstance(params[0], Wait)
    assert params[0].duration_s == 12.34
