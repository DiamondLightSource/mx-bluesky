from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol
from urllib.parse import quote, urlencode


class Metadata(StrEnum):
    """Metadata fields that can be specified by the caller when raising an alert."""

    CONTAINER = "container"
    SAMPLE_ID = "sample_id"
    VISIT = "visit"


class ExtraMetadata(StrEnum):
    """Additional metadata fields that are automatically appended by
    the AlertService implementations."""

    ALERT_CONTENT = "alert_content"
    ALERT_SUMMARY = "alert_summary"
    BEAMLINE = "beamline"
    GRAYLOG_URL = "graylog_url"
    ISPYB_URL = "ispyb_url"
    PROPOSAL = "proposal"


class AlertService(Protocol):
    """
    Implemented by any backend that provides the ability to dispatch alerts to some
    service that is capable of disseminating them via any of a variety of media such
    as email, SMS, instant messaging, etc etc.
    """

    def raise_alert(self, summary: str, content: str, metadata: dict[Metadata, str]):
        """
        Raise an alert that will be forwarded to beamline support staff, which might
        for example be used as the basis for an incident in an incident reporting system.
        Args:
            summary: One line summary of the alert, that might for instance be used
                in an email subject line.
            content: Plain text content detailing the nature of the incident.
            metadata: A dict of strings that can be included as metadata in the alert for
                those backends that support it. The summary and content will be included
                by default.
        """
        pass


_alert_service: AlertService


def get_alerting_service() -> AlertService:
    """Get the alert service for this instance."""
    return _alert_service


def set_alerting_service(service: AlertService):
    """Set the alert service for this instance, call when the beamline is initialised."""
    global _alert_service
    _alert_service = service


def ispyb_url(sample_id: str):
    return f"https://ispyb.diamond.ac.uk/samples/sid/{quote(sample_id)}"


def graylog_url(stream_id: str):
    now = datetime.now(UTC)
    from_utc = now - timedelta(minutes=5)
    from_timestamp = from_utc.isoformat()
    # Add 1 second for graylog timing jitter
    to_utc = now + timedelta(seconds=1)
    to_timestamp = to_utc.isoformat()
    query_string = urlencode(
        {
            "streams": stream_id,
            "rangetype": "absolute",
            "from": from_timestamp,
            "to": to_timestamp,
        }
    )
    return "https://graylog.diamond.ac.uk/search?" + query_string
