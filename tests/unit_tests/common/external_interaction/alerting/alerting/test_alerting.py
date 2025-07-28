import os
from datetime import datetime
from logging import INFO, WARNING
from unittest.mock import MagicMock, patch

import pytest

from mx_bluesky.common.external_interaction.alerting import (
    Metadata,
    get_alerting_service,
    set_alerting_service,
)
from mx_bluesky.common.external_interaction.alerting.log_based_service import (
    LoggingAlertService,
)
from mx_bluesky.hyperion.parameters.constants import CONST

EXPECTED_GRAYLOG_URL = (
    "https://graylog.diamond.ac.uk/search?streams=66264f5519ccca6d1c9e4e03&"
    "rangetype=absolute&"
    "from=2025-08-25T15%3A27%3A24%2B00%3A00&"
    "to=2025-08-25T15%3A32%3A24%2B00%3A00"
)


@pytest.fixture(autouse=True)
def fixup_time():
    with patch(
        "mx_bluesky.common.external_interaction.alerting._service.datetime",
        MagicMock(
            **{"now.return_value": datetime.fromisoformat("2025-08-25T15:32:24Z")}
        ),
    ) as patched_now:
        yield patched_now


@pytest.fixture(autouse=True)
def fixup_beamline():
    with patch.dict(os.environ, {"BEAMLINE": "i03"}):
        yield


@pytest.mark.parametrize("level", [WARNING, INFO])
@patch("mx_bluesky.common.external_interaction.alerting.log_based_service.LOGGER")
def test_logging_alerting_service_raises_a_log_message(mock_logger: MagicMock, level):
    set_alerting_service(LoggingAlertService(CONST.GRAYLOG_STREAM_ID, level))
    get_alerting_service().raise_alert("Test summary", "Test message", {})

    mock_logger.log.assert_called_once_with(
        level,
        "***ALERT*** summary=Test summary content=Test message",
        extra={
            Metadata.ALERT_SUMMARY: "Test summary",
            Metadata.ALERT_CONTENT: "Test message",
            Metadata.BEAMLINE: "i03",
            Metadata.GRAYLOG_URL: EXPECTED_GRAYLOG_URL,
        },
    )


@patch("mx_bluesky.common.external_interaction.alerting.log_based_service.LOGGER")
def test_logging_alerting_service_raises_a_log_message_with_additional_metadata_when_sample_id_present(
    mock_logger: MagicMock,
):
    set_alerting_service(LoggingAlertService(CONST.GRAYLOG_STREAM_ID, WARNING))
    get_alerting_service().raise_alert(
        "Test summary",
        "Test message",
        {"sample_id": "123456", "visit": "cm14451-2"},
    )

    mock_logger.log.assert_called_once_with(
        WARNING,
        "***ALERT*** summary=Test summary content=Test message",
        extra={
            Metadata.ALERT_SUMMARY: "Test summary",
            Metadata.ALERT_CONTENT: "Test message",
            Metadata.BEAMLINE: "i03",
            Metadata.GRAYLOG_URL: EXPECTED_GRAYLOG_URL,
            Metadata.ISPYB_URL: "https://ispyb.diamond.ac.uk/samples/sid/123456",
            Metadata.SAMPLE_ID: "123456",
            Metadata.PROPOSAL: "cm14451",
            Metadata.VISIT: "cm14451-2",
        },
    )
