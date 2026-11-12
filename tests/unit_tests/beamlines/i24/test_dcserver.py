from unittest.mock import patch

import pytest
import requests.exceptions
import responses

from mx_bluesky.beamlines.i24.dcserver import (
    DEFAULT_DCSERVER_URL,
    SERVER_ENV_VAR,
    TOKEN_ENV_VAR,
    DCServerError,
    create_data_collection,
    get_auth_header,
    get_dcserver_url,
    update_data_collection,
)
from tests.unit_tests.beamlines.i24.conftest import TEST_DCSERVER_URL


def test_the_production_server_is_used_by_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(SERVER_ENV_VAR, raising=False)
    assert get_dcserver_url() == DEFAULT_DCSERVER_URL


def test_the_server_can_be_overridden_by_environment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(SERVER_ENV_VAR, "https://other-dcserver.test")
    assert get_dcserver_url() == "https://other-dcserver.test"


def test_the_token_can_be_overridden_by_environment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(TOKEN_ENV_VAR, "a-test-token")
    assert get_auth_header() == {"Authorization": "Bearer a-test-token"}


def test_the_token_is_not_cached_between_calls(monkeypatch: pytest.MonkeyPatch):
    # A cached header would outlive the server it authenticates against, which defeats
    # the point of being able to move between them.
    monkeypatch.setenv(TOKEN_ENV_VAR, "first-token")
    assert get_auth_header()["Authorization"] == "Bearer first-token"
    monkeypatch.setenv(TOKEN_ENV_VAR, "second-token")
    assert get_auth_header()["Authorization"] == "Bearer second-token"


def test_the_token_is_read_from_the_key_file_when_the_environment_is_unset(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    monkeypatch.delenv(TOKEN_ENV_VAR, raising=False)
    key_file = tmp_path / "ssx_dcserver.key"
    key_file.write_text("a-key-file-token\n")
    monkeypatch.setattr(
        "mx_bluesky.beamlines.i24.dcserver.CREDENTIALS_LOCATION", str(key_file)
    )

    assert get_auth_header() == {"Authorization": "Bearer a-key-file-token"}


def test_no_credentials_warns_rather_than_failing(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    monkeypatch.delenv(TOKEN_ENV_VAR, raising=False)
    monkeypatch.setattr(
        "mx_bluesky.beamlines.i24.dcserver.CREDENTIALS_LOCATION",
        str(tmp_path / "not-a-file"),
    )

    assert get_auth_header() == {}


def test_an_unregistered_request_is_refused_rather_than_made():
    """The autouse RequestsMock in this tree's conftest, checked rather than assumed.

    The rotation plan posts as an ordinary call, so nothing but this stops a test that
    forgets to register a response from writing to the real ISPyB.
    """
    with pytest.raises(
        requests.exceptions.ConnectionError, match="Connection refused by Responses"
    ):
        create_data_collection({"visit": "cm12345-6"})


def test_the_server_and_token_used_are_the_overridden_ones(
    mock_requests: responses.RequestsMock,
):
    """No test should be able to reach the production server or read its credentials."""
    mock_requests.post(
        f"{TEST_DCSERVER_URL}/dc", json={"dataCollectionId": 1}, status=201
    )

    create_data_collection({"visit": "cm12345-6"})

    request = mock_requests.calls[0].request
    assert request.url == f"{TEST_DCSERVER_URL}/dc"
    assert request.headers["Authorization"] == "Bearer a-test-token"


def test_create_asks_for_autosample_only_when_told_to(
    mock_requests: responses.RequestsMock,
):
    mock_requests.post(
        f"{TEST_DCSERVER_URL}/dc", json={"dataCollectionId": 1}, status=201
    )

    create_data_collection({"visit": "cm12345-6"})
    create_data_collection({"visit": "cm12345-6"}, autosample=True)

    assert mock_requests.calls[0].request.url == f"{TEST_DCSERVER_URL}/dc"
    assert (
        mock_requests.calls[1].request.url == f"{TEST_DCSERVER_URL}/dc?autosample=true"
    )


def test_an_explicit_server_overrides_the_environment(
    mock_requests: responses.RequestsMock,
):
    mock_requests.post(
        "https://other-dcserver.test/dc", json={"dataCollectionId": 7}, status=201
    )
    mock_requests.patch("https://other-dcserver.test/dc/7", status=200)

    dcid = create_data_collection(
        {"visit": "cm12345-6"}, server="https://other-dcserver.test"
    )
    update_data_collection(dcid, {}, server="https://other-dcserver.test")

    assert dcid == 7


def test_update_patches_the_collection(mock_requests: responses.RequestsMock):
    mock_requests.patch(f"{TEST_DCSERVER_URL}/dc/1234", status=200)

    update_data_collection(1234, {"runStatus": "DataCollection Successful"})

    request = mock_requests.calls[0].request
    assert request.method == "PATCH"
    assert request.headers["Authorization"] == "Bearer a-test-token"
    assert request.body == b'{"runStatus": "DataCollection Successful"}'


def test_a_rejected_request_raises_with_what_the_server_said(
    mock_requests: responses.RequestsMock,
):
    mock_requests.patch(
        f"{TEST_DCSERVER_URL}/dc/1234", body="extra field: wibble", status=422
    )

    with pytest.raises(DCServerError, match="extra field: wibble") as e:
        update_data_collection(1234, {"wibble": 1})

    # Still an HTTPError carrying the response, as raise_for_status would give
    assert isinstance(e.value, requests.exceptions.HTTPError)
    assert e.value.response is not None
    assert e.value.response.status_code == 422


def test_unserialisable_data_is_logged_and_raised_before_sending(
    mock_requests: responses.RequestsMock,
):
    with (
        patch("mx_bluesky.beamlines.i24.dcserver.DCSERVER_LOGGER") as fake_logger,
        pytest.raises(TypeError),
    ):
        create_data_collection({"visit": object()})

    fake_logger.error.assert_called_once()
    assert len(mock_requests.calls) == 0
