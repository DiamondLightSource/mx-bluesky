from unittest.mock import MagicMock

import pytest
from flask import Flask
from flask.testing import FlaskClient

from mx_bluesky.common.parameters.constants import Status
from mx_bluesky.hyperion.plan_runner import PlanRunner
from mx_bluesky.hyperion.plan_runner_api import (
    create_app_for_udc,
)


@pytest.fixture()
def mock_runner():
    return MagicMock(spec=PlanRunner)


@pytest.fixture()
def app_under_test(mock_runner):
    app = create_app_for_udc(mock_runner)
    yield app


@pytest.fixture()
def client(app_under_test: Flask) -> FlaskClient:
    return app_under_test.test_client()


def test_plan_runner_api_triggers_shutdown(app_under_test, client, mock_runner):
    response = client.post("/shutdown")
    assert response.status_code == 200
    mock_runner.shutdown.assert_called_once()


def test_plan_runner_api_fetch_status(app_under_test, client, mock_runner):
    mock_runner.current_status = Status.BUSY
    response = client.get("/status")
    assert response.status_code == 200
    assert response.content_type == "application/json"
    assert response.json["status"] == Status.BUSY.value
