import json
from math import isclose
from pathlib import PosixPath
from unittest.mock import MagicMock, patch

import pytest
from dodal.devices.zebra.zebra import RotationDirection

from mx_bluesky.common.parameters.constants import GridscanParamConstants
from mx_bluesky.hyperion.external_interaction.agamemnon import (
    PinType,
    SinglePin,
    compare_params,
    create_parameters_from_agamemnon,
    get_next_instruction,
    get_pin_type_from_agamemnon_parameters,
    get_withenergy_parameters_from_agamemnon,
    get_withvisit_parameters_from_agamemnon,
    populate_parameters_from_agamemnon,
    update_params_from_agamemnon,
)
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
    pin = PinType(num_wells, well_width, buffer)
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
        get_pin_type_from_agamemnon_parameters(set_up_agamemnon_params()) == SinglePin()
    )


@pytest.mark.parametrize(
    "loop_name, expected_loop",
    [
        ("multipin_6x50+9", PinType(6, 50, 9)),
        ("multipin_6x25.8+8.6", PinType(6, 25.8, 8.6)),
        ("multipin_9x31+90", PinType(9, 31, 90)),
    ],
)
def test_given_multipin_loop_type_in_parameters_then_expected_pin_returned(
    loop_name: str, expected_loop: PinType
):
    assert (
        get_pin_type_from_agamemnon_parameters(set_up_agamemnon_params(loop_name))
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
        get_pin_type_from_agamemnon_parameters(set_up_agamemnon_params(loop_name))
        == SinglePin()
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
        get_pin_type_from_agamemnon_parameters(set_up_agamemnon_params(loop_name))
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
    get_next_instruction("i03")
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
        get_next_instruction("i03")
    assert "not_collect" in str(e.value)


@patch("mx_bluesky.hyperion.external_interaction.agamemnon.requests")
def test_given_agamemnon_returns_multipin_when_get_next_pin_type_from_agamemnon_called_then_multipin_returned(
    mock_requests: MagicMock,
):
    configure_mock_agamemnon(mock_requests, "multipin_6x50+98.1")
    params = get_next_instruction("i03")
    assert get_pin_type_from_agamemnon_parameters(params) == PinType(6, 50, 98.1)


@patch("mx_bluesky.hyperion.external_interaction.agamemnon.requests")
def test_given_agamemnon_fails_when_update_parameters_called_then_parameters_unchanged(
    mock_requests: MagicMock, load_centre_collect_params: LoadCentreCollect
):
    mock_requests.get.side_effect = Exception("Bad")
    old_grid_width = load_centre_collect_params.robot_load_then_centre.grid_width_um
    params = update_params_from_agamemnon(load_centre_collect_params)
    assert params.robot_load_then_centre.grid_width_um == old_grid_width


@patch("mx_bluesky.hyperion.external_interaction.agamemnon.compare_params")
@patch("mx_bluesky.hyperion.external_interaction.agamemnon.requests")
def test_given_agamemnon_gives_single_pin_when_update_parameters_called_then_parameters_changed_to_single_pin(
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
def test_given_agamemnon_gives_multi_pin_when_update_parameters_called_then_parameters_changed_to_multi_pin(
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
def test_given_set_of_parameters_then_correct_agamemnon_url_is_deduced(
    mock_requests: MagicMock, load_centre_collect_params: LoadCentreCollect
):
    update_params_from_agamemnon(load_centre_collect_params)
    mock_requests.get.assert_called_once_with(
        "http://agamemnon.diamond.ac.uk/getnextcollect/i03",
        headers={"Accept": "application/json"},
    )


@pytest.mark.parametrize(
    "prefix, expected_visit",
    [
        ["/dls/i03/data/2025/mx23694-130/foo/bar", "mx23694-130"],
        ["/dls/not-i03/data/2021/mx84743-230", "mx84743-230"],
    ],
)
def test_given_valid_prefix_then_correct_visit_is_set(prefix: str, expected_visit: str):
    visit, _ = get_withvisit_parameters_from_agamemnon(
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
        get_withvisit_parameters_from_agamemnon(
            set_up_agamemnon_params(None, prefix, None)
        )

    assert "MX-General root structure" in str(e.value)


def test_no_prefix_raises_exception():
    with pytest.raises(KeyError) as e:
        get_withvisit_parameters_from_agamemnon({"not_collect": ""})

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
    "mx_bluesky.hyperion.external_interaction.agamemnon.populate_parameters_from_agamemnon"
)
def test_if_failed_to_populate_parameters_from_hyperion_exception_is_logged(
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


@pytest.mark.parametrize(
    "agamemnon_params",
    ["example_collect.json", "example_collect_multipin.json"],
)
@patch("mx_bluesky.hyperion.external_interaction.agamemnon.LOGGER")
@patch("mx_bluesky.hyperion.external_interaction.agamemnon.requests")
@patch("mx_bluesky.common.parameters.components.os", new=MagicMock())
@patch("mx_bluesky.hyperion.parameters.rotation.os", new=MagicMock())
@patch("dodal.devices.detector.detector.Path", new=MagicMock())
@patch("dodal.utils.os", new=MagicMock())
def test_populate_parameters_from_agamemnon_causes_no_warning_when_compared_to_gda_params(
    mock_requests: MagicMock,
    mock_logger: MagicMock,
    agamemnon_params: str,
    load_centre_collect_params: LoadCentreCollect,
):
    with open(f"tests/test_data/agamemnon/{agamemnon_params}") as json_file:
        example_json = json_file.read()
        mock_requests.get.return_value.content = example_json

    compare_params(load_centre_collect_params)
    mock_logger.warning.assert_not_called()


@patch("mx_bluesky.hyperion.external_interaction.agamemnon.requests")
@patch("mx_bluesky.common.parameters.components.os", new=MagicMock())
def test_populate_parameters_from_agamemnon_contains_expected_data(
    mock_requests: MagicMock,
):
    with open("tests/test_data/agamemnon/example_collect.json") as json_file:
        example_json = json_file.read()
        mock_requests.get.return_value.content = example_json

    agamemnon_params = get_next_instruction("i03")
    hyperion_params = populate_parameters_from_agamemnon(agamemnon_params)
    assert hyperion_params.visit == "cm00000-0"
    assert isclose(hyperion_params.detector_distance_mm, 180.8)  # type: ignore
    assert hyperion_params.sample_id == 12345
    assert hyperion_params.sample_puck == 40
    assert hyperion_params.sample_pin == 3
    assert str(hyperion_params.parameter_model_version) == "5.3.0"
    assert hyperion_params.select_centres.n == 1


@patch("mx_bluesky.hyperion.external_interaction.agamemnon.requests")
@patch("mx_bluesky.common.parameters.components.os", new=MagicMock())
def test_populate_parameters_from_agamemnon_contains_expected_robot_load_then_centre_data(
    mock_requests: MagicMock,
):
    with open("tests/test_data/agamemnon/example_collect.json") as json_file:
        example_json = json_file.read()
        mock_requests.get.return_value.content = example_json

    agamemnon_params = get_next_instruction("i03")
    hyperion_params = populate_parameters_from_agamemnon(agamemnon_params)
    robot_load_params = hyperion_params.robot_load_then_centre
    assert robot_load_params.visit == "cm00000-0"
    assert isclose(robot_load_params.detector_distance_mm, 180.8)  # type: ignore
    assert robot_load_params.sample_id == 12345
    assert robot_load_params.sample_puck == 40
    assert robot_load_params.sample_pin == 3
    assert robot_load_params.demand_energy_ev == 12700.045934258673
    assert robot_load_params.omega_start_deg == 0.0
    assert robot_load_params.chi_start_deg == 0.0
    assert robot_load_params.transmission_frac == 1.0
    assert robot_load_params.tip_offset_um == 300.0
    assert robot_load_params.grid_width_um == 600.0
    assert robot_load_params.features.use_gpu_results
    assert str(robot_load_params.parameter_model_version) == "5.3.0"
    assert (
        robot_load_params.storage_directory
        == "/dls/tmp/data/year/cm00000-0/auto/test/xraycentring"
    )
    assert robot_load_params.file_name == "test_xtal"
    assert robot_load_params.snapshot_directory == PosixPath(
        "/dls/tmp/data/year/cm00000-0/auto/test/xraycentring/snapshots"
    )


@patch("mx_bluesky.hyperion.external_interaction.agamemnon.requests")
@patch("mx_bluesky.common.parameters.components.os", new=MagicMock())
@patch("mx_bluesky.hyperion.parameters.rotation.os", new=MagicMock())
@patch("dodal.devices.detector.detector.Path", new=MagicMock())
def test_populate_parameters_from_agamemnon_contains_expected_rotation_data(
    mock_requests: MagicMock,
):
    with open("tests/test_data/agamemnon/example_collect.json") as json_file:
        example_json = json_file.read()
        mock_requests.get.return_value.content = example_json

    agamemnon_params = get_next_instruction("i03")
    hyperion_params = populate_parameters_from_agamemnon(agamemnon_params)
    rotation_params = hyperion_params.multi_rotation_scan
    assert rotation_params.visit == "cm00000-0"
    assert isclose(rotation_params.detector_distance_mm, 180.8)  # type: ignore
    assert rotation_params.detector_params.omega_start == 0.0
    assert rotation_params.detector_params.exposure_time_s == 0.002
    assert rotation_params.detector_params.num_images_per_trigger == 3600
    assert rotation_params.num_images == 3600
    assert rotation_params.transmission_frac == 0.5
    assert rotation_params.comment == "Complete_P1_sweep1 "
    assert rotation_params.ispyb_experiment_type == "Characterization"

    assert rotation_params.sample_puck == 40
    assert rotation_params.sample_pin == 3

    individual_scans = list(rotation_params.single_rotation_scans)
    assert len(individual_scans) == 1
    assert individual_scans[0].scan_points["omega"][1] == 0.1
    assert individual_scans[0].phi_start_deg == 0.0
    assert individual_scans[0].chi_start_deg == 0.0
    assert individual_scans[0].rotation_direction == RotationDirection.POSITIVE

    assert rotation_params.demand_energy_ev == 12700.045934258673
    assert str(rotation_params.parameter_model_version) == "5.3.0"
    assert rotation_params.storage_directory == "/dls/tmp/data/year/cm00000-0/auto/test"
    assert rotation_params.file_name == "test_xtal"
    assert rotation_params.snapshot_directory == PosixPath(
        "/dls/tmp/data/year/cm00000-0/auto/test/snapshots"
    )


@patch("mx_bluesky.hyperion.external_interaction.agamemnon.requests")
@patch("mx_bluesky.common.parameters.components.os", new=MagicMock())
def test_populate_multipin_parameters_from_agamemnon(
    mock_requests: MagicMock,
):
    with open("tests/test_data/agamemnon/example_collect_multipin.json") as json_file:
        example_json = json_file.read()
        mock_requests.get.return_value.content = example_json

    agamemnon_params = get_next_instruction("i03")
    hyperion_params = populate_parameters_from_agamemnon(agamemnon_params)
    assert hyperion_params.select_centres.n == 6


@patch("mx_bluesky.hyperion.external_interaction.agamemnon.requests")
@patch("mx_bluesky.common.parameters.components.os", new=MagicMock())
def test_get_withenergy_parameters_from_agamemnon(mock_requests: MagicMock):
    with open("tests/test_data/agamemnon/example_collect.json") as json_file:
        example_json = json_file.read()
        mock_requests.get.return_value.content = example_json

    agamemnon_params = get_next_instruction("i03")
    demand_energy_ev = get_withenergy_parameters_from_agamemnon(agamemnon_params)
    assert demand_energy_ev["demand_energy_ev"] == 12700.045934258673


def test_get_withenergy_parameters_from_agamemnon_when_no_wavelength():
    agamemnon_params = {}
    demand_energy_ev = get_withenergy_parameters_from_agamemnon(agamemnon_params)
    assert demand_energy_ev["demand_energy_ev"] is None


@patch("mx_bluesky.hyperion.external_interaction.agamemnon.requests")
def test_create_parameters_from_agamemnon_returns_none_if_queue_is_empty(
    mock_requests,
):
    mock_requests.get.return_value.content = json.dumps({"collect": {}})
    params = create_parameters_from_agamemnon()
    assert params is None


@patch("mx_bluesky.hyperion.external_interaction.agamemnon.requests")
@patch("mx_bluesky.common.parameters.components.os", new=MagicMock())
def test_create_parameters_from_agamemnon_does_not_return_none_if_queue_is_not_empty(
    mock_requests: MagicMock,
):
    with open("tests/test_data/agamemnon/example_collect_multipin.json") as json_file:
        example_json = json_file.read()
        mock_requests.get.return_value.content = example_json
    params = create_parameters_from_agamemnon()
    assert params is not None
