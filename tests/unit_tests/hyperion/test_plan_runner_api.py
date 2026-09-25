from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mx_bluesky.common.parameters.constants import Status
from mx_bluesky.hyperion.in_process_runner import InProcessRunner
from mx_bluesky.hyperion.plan_runner_api import app


@pytest.fixture()
def mock_runner():
    runner = MagicMock(spec=InProcessRunner)
    with patch("mx_bluesky.hyperion.plan_runner_api._plan_runner", runner, create=True):
        yield runner


@pytest.fixture()
def app_under_test(mock_runner):
    yield app


@pytest.fixture()
def client(app_under_test: FastAPI) -> TestClient:
    return TestClient(app_under_test)


def test_plan_runner_api_fetch_status(app_under_test, client, mock_runner):
    mock_runner.current_status = Status.BUSY
    response = client.get("/status")
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "application/json"
    assert response.json()["status"] == Status.BUSY.value


def test_plan_runner_api_callback_liveness(app_under_test, client, mock_runner):
    response = client.get("/callbackPing")
    mock_runner.reset_callback_watchdog_timer.assert_called_once()
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "application/json"
