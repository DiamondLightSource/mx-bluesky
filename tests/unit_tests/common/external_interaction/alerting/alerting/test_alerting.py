from datetime import datetime
from logging import INFO, WARNING
from unittest.mock import MagicMock, patch

import pytest

from mx_bluesky.common.external_interaction.alerting import (
    get_alerting_service,
    set_alerting_service,
)
from mx_bluesky.common.external_interaction.alerting.log_based_service import (
    LoggingAlertService,
)

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


@pytest.mark.parametrize("level", [WARNING, INFO])
@patch("mx_bluesky.common.external_interaction.alerting.log_based_service.LOGGER")
def test_logging_alerting_service_raises_a_log_message(mock_logger: MagicMock, level):
    set_alerting_service(LoggingAlertService(level))
    get_alerting_service().raise_alert(
        "Test summary", "Test message", {"alert_type": "Test"}
    )

    mock_logger.log.assert_called_once_with(
        level,
        "***ALERT*** summary=Test summary content=Test message",
        extra={
            "alert_summary": "Test summary",
            "alert_content": "Test message",
            "alert_type": "Test",
            "graylog_url": EXPECTED_GRAYLOG_URL,
        },
    )


@patch("mx_bluesky.common.external_interaction.alerting.log_based_service.LOGGER")
def test_logging_alerting_service_raises_a_log_message_with_additional_metadata_when_sample_id_present(
    mock_logger: MagicMock,
):
    set_alerting_service(LoggingAlertService(WARNING))
    get_alerting_service().raise_alert(
        "Test summary", "Test message", {"alert_type": "Test", "sample_id": "123456"}
    )

    mock_logger.log.assert_called_once_with(
        WARNING,
        "***ALERT*** summary=Test summary content=Test message",
        extra={
            "alert_summary": "Test summary",
            "alert_content": "Test message",
            "alert_type": "Test",
            "graylog_url": EXPECTED_GRAYLOG_URL,
            "ispyb_url": "https://ispyb.diamond.ac.uk/samples/sid/123456",
            "sample_id": "123456",
        },
    )
