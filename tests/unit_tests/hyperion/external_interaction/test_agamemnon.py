import json
from collections.abc import Generator
from math import isclose
from pathlib import PosixPath
from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from dodal.devices.zebra.zebra import RotationDirection

from mx_bluesky.hyperion._plan_runner_params import Wait
from mx_bluesky.hyperion.blueapi.parameters import (
    LoadCentreCollectParams,
    MultiSamplePinTypeParam,
    PinTypeParam,
    SingleSamplePinTypeParam,
    load_centre_collect_to_internal,
)
from mx_bluesky.hyperion.external_interaction.agamemnon import (
    _get_next_instruction,
    _get_pin_type_from_agamemnon_collect_parameters,
    _get_withenergy_parameters_from_agamemnon,
    _get_withvisit_parameters_from_agamemnon,
    _instruction_and_data,
    create_parameters_from_agamemnon,
)


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
        == SingleSamplePinTypeParam()
    )


@pytest.mark.parametrize(
    "loop_name, expected_loop",
    [
        (
            "multipin_6x50+9",
            MultiSamplePinTypeParam(wells=6, well_size_um=50, tip_to_first_well_um=9),
        ),
        (
            "multipin_6x25.8+8.6",
            MultiSamplePinTypeParam(
                wells=6, well_size_um=25.8, tip_to_first_well_um=8.6
            ),
        ),
        (
            "multipin_9x31+90",
            MultiSamplePinTypeParam(wells=9, well_size_um=31, tip_to_first_well_um=90),
        ),
    ],
)
def test_given_multipin_loop_type_in_parameters_then_expected_pin_returned(
    loop_name: str, expected_loop: PinTypeParam
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
        == SingleSamplePinTypeParam()
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
    assert _get_pin_type_from_agamemnon_collect_parameters(
        params
    ) == MultiSamplePinTypeParam(wells=6, well_size_um=50, tip_to_first_well_um=98.1)


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
    ["tests/test_data/agamemnon/example_native.json"],
    indirect=True,
)
def test_create_parameters_from_agamemnon_contains_expected_data(agamemnon_response):
    hyperion_params_list = create_parameters_from_agamemnon()
    for hyperion_params in hyperion_params_list:
        assert isinstance(hyperion_params, LoadCentreCollectParams)
        assert hyperion_params.visit == "mx34598-77"
        assert isclose(hyperion_params.detector_distance_mm, 237.017, abs_tol=1e-3)  # type: ignore
        assert hyperion_params.sample_id == 6501159
        assert hyperion_params.sample_puck == 5
        assert hyperion_params.sample_pin == 4
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
        load_centre_collect_to_internal(p)
        for p in hyperion_params_list
        if isinstance(p, LoadCentreCollectParams)
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


@patch("mx_bluesky.common.parameters.rotation.os", new=MagicMock())
@patch("dodal.devices.detector.detector.Path", new=MagicMock())
@pytest.mark.parametrize(
    "agamemnon_response",
    ["tests/test_data/agamemnon/example_native.json"],
    indirect=True,
)
def test_create_parameters_from_agamemnon_contains_expected_rotation_data(
    agamemnon_response,
):
    hyperion_params_list = [
        load_centre_collect_to_internal(cast(LoadCentreCollectParams, p))
        for p in create_parameters_from_agamemnon()
    ]  # type: ignore
    assert len(hyperion_params_list) == 2
    for hyperion_params in hyperion_params_list:
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
