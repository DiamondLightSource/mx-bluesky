import datetime
import json
from unittest.mock import patch

import pytest
import requests
import responses
from dodal.devices.beamlines.i24.beam_center import DetectorBeamCenter
from dodal.devices.beamlines.i24.dcm import DCM
from dodal.devices.beamlines.i24.focus_mirrors import FocusMirrorsMode
from ophyd_async.core import set_mock_value

from mx_bluesky.beamlines.i24.serial.dcid import (
    DCID,
    get_resolution,
    read_beam_info_from_hardware,
)
from mx_bluesky.beamlines.i24.serial.parameters import (
    BeamSettings,
    DetectorName,
    ExtruderParameters,
)
from mx_bluesky.beamlines.i24.serial.parameters.constants import SSXType
from mx_bluesky.beamlines.i24.serial.setup_beamline import Eiger
from tests.unit_tests.beamlines.i24.conftest import TEST_DCSERVER_URL


def test_read_beam_info_from_hardware(
    dcm: DCM,
    mirrors: FocusMirrorsMode,
    eiger_beam_center: DetectorBeamCenter,
    run_engine,
):
    set_mock_value(dcm.wavelength_in_a.user_readback, 0.6)
    expected_beam_x = 1605 * 0.075
    expected_beam_y = 1702 * 0.075

    res = run_engine(
        read_beam_info_from_hardware(
            dcm, mirrors, eiger_beam_center, DetectorName.EIGER
        )
    ).plan_result  # type: ignore

    assert res.wavelength_in_a == 0.6
    assert res.beam_size_in_um == (7, 7)
    assert res.beam_center_in_mm == (expected_beam_x, expected_beam_y)


def test_get_resolution():
    distance = 100
    wavelength = 0.649

    eiger_resolution = get_resolution(Eiger(), distance, wavelength)

    assert eiger_resolution == 0.78


@pytest.fixture
def beam_settings() -> BeamSettings:
    return BeamSettings(
        wavelength_in_a=0.6, beam_size_in_um=(7, 7), beam_center_in_mm=(100, 100)
    )


@patch("mx_bluesky.beamlines.i24.serial.dcid.get_resolution")
def test_generate_dcid_for_eiger(
    patch_resolution,
    dummy_params_ex,
    beam_settings,
    mock_requests: responses.RequestsMock,
):
    mock_requests.post(
        f"{TEST_DCSERVER_URL}/dc", json={"dataCollectionId": 1234}, status=201
    )
    patch_resolution.return_value = 1.5
    test_dcid = DCID(emit_errors=True, expt_params=dummy_params_ex)

    assert isinstance(test_dcid.detector, Eiger)
    assert isinstance(test_dcid.parameters, ExtruderParameters)

    test_dcid.generate_dcid(beam_settings, "", "protein.nxs", 10)

    patch_resolution.assert_called_once_with(
        test_dcid.detector,
        dummy_params_ex.detector_distance_mm,
        beam_settings.wavelength_in_a,
    )
    assert test_dcid.dcid == 1234
    assert not test_dcid.error

    request = mock_requests.calls[0].request
    assert request.url == f"{TEST_DCSERVER_URL}/dc?autosample=true"
    assert request.headers["Authorization"] == "Bearer a-test-token"
    body = json.loads(request.body)  # type: ignore
    expt_type = body["group"]["experimentType"]
    assert (
        not isinstance(expt_type, SSXType)  # needs to be serialisable
        and expt_type == dummy_params_ex.ispyb_experiment_type.value
    )
    assert body["detectorId"] == 94
    assert body["resolution"] == 1.5
    assert "beamSizeAtSampleX" in body
    assert len(body["ssx"]["eventChain"]["events"]) == 1  # no pump probe


def test_generate_dcid_uses_an_explicit_server(
    dummy_params_ex, beam_settings, mock_requests: responses.RequestsMock
):
    mock_requests.post(
        "https://other-dcserver.test/dc", json={"dataCollectionId": 1}, status=201
    )
    test_dcid = DCID(
        server="https://other-dcserver.test",
        emit_errors=True,
        expt_params=dummy_params_ex,
    )

    test_dcid.generate_dcid(beam_settings, "", "protein.nxs", 10)

    assert test_dcid.dcid == 1


@patch("mx_bluesky.beamlines.i24.serial.dcid.SSX_LOGGER")
def test_generate_dcid_failure_is_logged_not_raised(
    fake_log, dummy_params_ex, beam_settings, mock_requests: responses.RequestsMock
):
    mock_requests.post(f"{TEST_DCSERVER_URL}/dc", body="no such visit", status=422)
    test_dcid = DCID(emit_errors=False, expt_params=dummy_params_ex)

    test_dcid.generate_dcid(beam_settings, "", "protein.nxs", 10)

    assert test_dcid.dcid is None
    assert test_dcid.error
    fake_log.error.assert_called_once_with(
        "DCID generation Failed; Reason from server: %s", "no such visit"
    )


def test_generate_dcid_failure_raises_http_error_when_emitting_errors(
    dummy_params_ex, beam_settings, mock_requests: responses.RequestsMock
):
    mock_requests.post(f"{TEST_DCSERVER_URL}/dc", body="no such visit", status=422)
    test_dcid = DCID(emit_errors=True, expt_params=dummy_params_ex)

    with pytest.raises(requests.HTTPError, match="no such visit"):
        test_dcid.generate_dcid(beam_settings, "", "protein.nxs", 10)
    assert test_dcid.error


@pytest.mark.parametrize(
    "aborted, status",
    [(False, "DataCollection Successful"), (True, "DataCollection Cancelled")],
)
def test_collection_complete_patches_the_dcid(
    aborted, status, dummy_params_ex, mock_requests: responses.RequestsMock
):
    mock_requests.patch(f"{TEST_DCSERVER_URL}/dc/1234", status=200)
    test_dcid = DCID(emit_errors=True, expt_params=dummy_params_ex)
    test_dcid.dcid = 1234
    end_time = datetime.datetime(2026, 11, 12, 10, 30, tzinfo=datetime.UTC)

    test_dcid.collection_complete(end_time, aborted=aborted)

    request = mock_requests.calls[0].request
    assert request.headers["Authorization"] == "Bearer a-test-token"
    assert json.loads(request.body) == {  # type: ignore
        "endTime": end_time.isoformat(),
        "runStatus": status,
    }
    assert not test_dcid.error


def test_collection_complete_without_a_dcid_sends_nothing(
    dummy_params_ex, mock_requests: responses.RequestsMock
):
    test_dcid = DCID(emit_errors=True, expt_params=dummy_params_ex)

    test_dcid.collection_complete(aborted=False)

    assert len(mock_requests.calls) == 0
    assert not test_dcid.error


@patch("mx_bluesky.beamlines.i24.serial.dcid.SSX_LOGGER")
def test_collection_complete_failure_is_logged_with_the_server_response(
    fake_log, dummy_params_ex, mock_requests: responses.RequestsMock
):
    mock_requests.patch(f"{TEST_DCSERVER_URL}/dc/1234", body="gone", status=404)
    test_dcid = DCID(emit_errors=False, expt_params=dummy_params_ex)
    test_dcid.dcid = 1234

    test_dcid.collection_complete(aborted=False)

    assert test_dcid.error
    fake_log.warning.assert_called_once()
    assert fake_log.warning.call_args.args[-1] == "gone"
