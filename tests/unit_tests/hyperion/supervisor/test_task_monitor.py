from time import sleep
from unittest.mock import ANY, Mock, patch

import pytest
from blueapi.client import BlueapiClient
from blueapi.service.model import TaskRequest
from blueapi.worker import ProgressEvent, StatusView

from mx_bluesky.common.external_interaction.alerting import Metadata
from mx_bluesky.hyperion.supervisor._task_monitor import TaskMonitor

from ....conftest import TEST_VISIT


@pytest.fixture(autouse=True)
def default_beamline(monkeypatch):
    monkeypatch.setenv("BEAMLINE", "i03")


@pytest.fixture
def task_request(external_load_centre_collect_params) -> TaskRequest:
    return TaskRequest(
        name="load_centre_collect",
        params={"parameters": external_load_centre_collect_params},
        instrument_session=TEST_VISIT,
    )


@pytest.fixture
def mock_alerting_service():
    with patch(
        "mx_bluesky.hyperion.supervisor._task_monitor.get_alerting_service"
    ) as mock_get_alerting_service:
        mock_alerting_service = mock_get_alerting_service.return_value
        yield mock_alerting_service


@patch(
    "mx_bluesky.hyperion.supervisor._task_monitor.TaskMonitor.DEFAULT_TIMEOUT_S", 0.25
)
def test_task_monitor_alerts_if_waiting_for_beam(mock_alerting_service, task_request):
    blueapi_client = Mock(spec=BlueapiClient)
    monitor = TaskMonitor(blueapi_client, task_request)
    with monitor:
        monitor.on_blueapi_event(
            ProgressEvent(
                task_id="12345",
                statuses={
                    "12345": StatusView(
                        display_name=TaskMonitor.FEEDBACK_STATUS_NAME,
                        current=0,
                        initial=0,
                        target=1,
                    )
                },
            )
        )
        sleep(0.5)
    blueapi_client.abort.assert_not_called()
    mock_alerting_service.raise_alert.assert_called_once_with(
        "Hyperion is paused waiting for beam on i03.",
        "Hyperion has been paused waiting for beam for 0 minutes.",
        {
            Metadata.SAMPLE_ID: 5461074,
            Metadata.VISIT: "cm31105-4",
            Metadata.CONTAINER: 2,
        },
    )


@patch(
    "mx_bluesky.hyperion.supervisor._task_monitor.TaskMonitor.DEFAULT_TIMEOUT_S", 0.25
)
def test_task_monitor_alerts_and_cancels_request_if_stuck_not_waiting_for_beam(
    mock_alerting_service, task_request
):
    blueapi_client = Mock(spec=BlueapiClient)
    monitor = TaskMonitor(blueapi_client, task_request)
    with monitor:
        monitor.on_blueapi_event(
            ProgressEvent(
                task_id="12345",
                statuses={
                    "12345": StatusView(
                        display_name=TaskMonitor.FEEDBACK_STATUS_NAME,
                        current=0,
                        initial=0,
                        target=1,
                    )
                },
            )
        )
        sleep(0.1)
        monitor.on_blueapi_event(
            ProgressEvent(
                task_id="12345",
                statuses={
                    "12345": StatusView(
                        display_name=TaskMonitor.FEEDBACK_STATUS_NAME,
                        current=1,
                        initial=0,
                        target=1,
                    )
                },
            )
        )
        sleep(0.5)
    blueapi_client.abort.assert_called_with(ANY)
    mock_alerting_service.raise_alert.assert_called_once_with(
        "UDC encountered an error on i03",
        "Hyperion Supervisor detected that BlueAPI was stuck for 0.25 seconds.",
        {
            Metadata.SAMPLE_ID: 5461074,
            Metadata.VISIT: "cm31105-4",
            Metadata.CONTAINER: 2,
        },
    )
