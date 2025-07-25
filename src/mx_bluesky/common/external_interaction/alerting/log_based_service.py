import logging

from dodal.log import LOGGER

from mx_bluesky.common.external_interaction.alerting import Metadata
from mx_bluesky.common.external_interaction.alerting._service import (
    graylog_url,
    ispyb_url,
)


class LoggingAlertService:
    """
    Implement an alert service that raises alerts by generating a specially formatted
    log message, that may be intercepted by a logging service such as graylog and
    used to dispatch the alert.
    """

    def __init__(self, level=logging.WARNING):
        """
        Create a new instance of the service
        Args:
            level: The python logging level at which to generate the message
        """
        super().__init__()
        self._level = level

    def _append_additional_metadata(self, metadata: dict[str, str]):
        metadata["graylog_url"] = graylog_url()
        if sample_id := metadata.get(Metadata.SAMPLE_ID, None):
            metadata["ispyb_url"] = ispyb_url(sample_id)

    def raise_alert(self, summary: str, content: str, metadata: dict[str, str]):
        message = f"***ALERT*** summary={summary} content={content}"
        self._append_additional_metadata(metadata)
        LOGGER.log(
            self._level,
            message,
            extra={"alert_summary": summary, "alert_content": content} | metadata,
        )
