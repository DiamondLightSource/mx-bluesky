import time
from threading import Timer
from typing import Self

from blueapi.client import BlueapiClient
from blueapi.client.event_bus import AnyEvent
from blueapi.service.model import TaskRequest
from blueapi.worker import ProgressEvent
from dodal.utils import get_beamline_name
from pydantic import BaseModel

from mx_bluesky.common.external_interaction.alerting import (
    Metadata,
    get_alerting_service,
)
from mx_bluesky.common.utils.log import LOGGER


class TaskMonitor:
    """
    Implements a context manager that on entry sets a timer for the BlueAPI Task to be executed within the with-block.
    The body should register on_blueapi_event as an event handler in the call to blueapi_client.run_task().

    If the timer expires before task completion, we either:
       * raise an error alert and cancel the task
       * raise an alert and reset the timer
    depending on whether received events indicate the task is waiting on a long-running event e.g. waiting for beam,
    or whether it is unexpectedly stuck.
    """

    DEFAULT_TIMEOUT_S = 1200
    FEEDBACK_STATUS_NAME = "xbpm_feedback-pos_stable"

    def __init__(self, blueapi_client: BlueapiClient, task_request: TaskRequest):
        self._task_request = task_request
        self._alerting_service = get_alerting_service()
        self._blueapi_client = blueapi_client
        self._is_waiting_for_beam: bool = False
        self._timer = None

    def __enter__(self) -> Self:
        self._is_waiting_for_beam = False
        self._start_time = time.monotonic()
        self._reset_timer()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._timer:
            self._timer.cancel()

    def on_blueapi_event(self, event: AnyEvent):
        match event:
            case ProgressEvent(statuses=statuses):
                feedback_statuses = [
                    s
                    for s in statuses.values()
                    if s.display_name == self.FEEDBACK_STATUS_NAME
                ]
                if feedback_statuses:
                    feedback_status = feedback_statuses[0]
                    waiting_for_beam = feedback_status.current != feedback_status.target
                    LOGGER.debug(
                        f"Waiting for beam {self._is_waiting_for_beam} -> {waiting_for_beam}, feedback_status = {feedback_status}"
                    )
                    if self._is_waiting_for_beam != waiting_for_beam:
                        self._reset_timer()
                        self._is_waiting_for_beam = waiting_for_beam
                    LOGGER.debug(
                        f"Hyperion blueapi reports waiting for feedback status: {self._is_waiting_for_beam}"
                    )

    def on_timeout_expiry(self):
        LOGGER.debug("Timer expired")
        if not self._is_waiting_for_beam:
            self._cancel_request()
            self._raise_alert_collection_is_stuck()
        else:
            LOGGER.debug("Raising waiting for feedback alert")
            self._reset_timer()
            self._raise_alert_collection_is_waiting_for_beam()

    def _reset_timer(self):
        if self._timer:
            self._timer.cancel()
        self._timer = Timer(self.DEFAULT_TIMEOUT_S, self.on_timeout_expiry)
        self._timer.start()

    def _raise_alert_collection_is_stuck(self):
        beamline = get_beamline_name("")
        self._alerting_service.raise_alert(
            f"UDC encountered an error on {beamline}",
            f"Hyperion Supervisor detected that BlueAPI was stuck for {self.DEFAULT_TIMEOUT_S} seconds.",
            self._extract_metadata(),
        )

    def _raise_alert_collection_is_waiting_for_beam(self):
        now = time.monotonic()
        minutes = int((now - self._start_time) // 60)
        beamline = get_beamline_name("")
        metadata = self._extract_metadata()
        LOGGER.info(
            f"Message is Hyperion is paused waiting for beam on {beamline}. Hyperion has been paused waiting for beam for {minutes} minutes."
        )
        self._alerting_service.raise_alert(
            f"Hyperion is paused waiting for beam on {beamline}.",
            f"Hyperion has been paused waiting for beam for {minutes} minutes.",
            metadata,
        )

    def _extract_metadata(self) -> dict[Metadata, str]:
        match self._task_request.params:
            case {"parameters": parameters}:
                if isinstance(parameters, BaseModel):
                    match parameters.model_dump():
                        case {
                            "sample_id": sample_id,
                            "visit": visit,
                            "sample_puck": container,
                        }:
                            return {
                                Metadata.SAMPLE_ID: str(sample_id),
                                Metadata.VISIT: str(visit),
                                Metadata.CONTAINER: str(container),
                            }
        return {}

    def _cancel_request(self):
        self._blueapi_client.abort(
            f"Hyperion Supervisor detected that BlueAPI was stuck for {self.DEFAULT_TIMEOUT_S} seconds."
        )
