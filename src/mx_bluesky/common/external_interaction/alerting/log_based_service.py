import logging
from typing import cast

from dodal.log import LOGGER
from dodal.utils import get_beamline_name

from mx_bluesky.common.external_interaction.alerting import Metadata
from mx_bluesky.common.external_interaction.alerting._service import (
    ExtraMetadata,
    graylog_url,
    ispyb_url,
)
from mx_bluesky.common.external_interaction.callbacks.common.ispyb_mapping import (
    get_proposal_and_session_from_visit_string,
)


class LoggingAlertService:
    """
    Implement an alert service that raises alerts by generating a specially formatted
    log message, that may be intercepted by a logging service such as graylog and
    used to dispatch the alert.
    """

    def __init__(self, graylog_stream_id: str, level=logging.WARNING):
        """
        Create a new instance of the service
        Args:
            level: The python logging level at which to generate the message
        """
        super().__init__()
        self._level = level
        self._graylog_stream_id = graylog_stream_id

    def _append_extra_metadata(self, metadata: dict[Metadata, str]) -> dict[str, str]:
        with_extras = cast(dict, metadata.copy())
        with_extras[ExtraMetadata.GRAYLOG_URL] = graylog_url(self._graylog_stream_id)
        with_extras[ExtraMetadata.BEAMLINE] = get_beamline_name("")
        if sample_id := metadata.get(Metadata.SAMPLE_ID, None):
            with_extras[ExtraMetadata.ISPYB_URL] = ispyb_url(sample_id)
        if visit := metadata.get(Metadata.VISIT, None):
            proposal, _ = get_proposal_and_session_from_visit_string(visit)
            with_extras[ExtraMetadata.PROPOSAL] = proposal
        return with_extras

    def raise_alert(self, summary: str, content: str, metadata: dict[Metadata, str]):
        message = f"***ALERT*** summary={summary} content={content}"
        with_extras = self._append_extra_metadata(metadata)
        LOGGER.log(
            self._level,
            message,
            extra={
                ExtraMetadata.ALERT_SUMMARY: summary,
                ExtraMetadata.ALERT_CONTENT: content,
            }
            | with_extras,
        )
