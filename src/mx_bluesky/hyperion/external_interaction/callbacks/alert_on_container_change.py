from dodal.utils import get_beamline_name
from event_model import Event, EventDescriptor, RunStart, RunStop

from mx_bluesky.common.external_interaction.alerting import (
    Metadata,
    get_alerting_service,
)
from mx_bluesky.common.external_interaction.callbacks.common.plan_reactive_callback import (
    PlanReactiveCallback,
)
from mx_bluesky.common.utils.log import ISPYB_ZOCALO_CALLBACK_LOGGER
from mx_bluesky.hyperion.parameters.constants import CONST


class AlertOnContainerChange(PlanReactiveCallback):
    """Sends an alert to beamline staff when a pin from a new puck has been loaded.
    This tends to be used as a heartbeat so we know that UDC is running."""

    def __init__(self):
        super().__init__(log=ISPYB_ZOCALO_CALLBACK_LOGGER)
        self._new_container = None
        self._visit = None
        self._sample_id = None
        self.descriptors: dict[str, EventDescriptor] = {}

    def activity_gated_descriptor(self, doc: EventDescriptor) -> EventDescriptor | None:
        self.descriptors[doc["uid"]] = doc
        return super().activity_gated_descriptor(doc)

    def activity_gated_event(self, doc: Event) -> Event | None:
        event_descriptor = self.descriptors.get(doc["descriptor"])
        if (
            event_descriptor
            and event_descriptor.get("name") == CONST.DESCRIPTORS.ROBOT_PRE_LOAD
        ):
            current_container = int(doc["data"]["robot-current_puck"])
            if self._new_container != current_container:
                beamline = get_beamline_name("")
                get_alerting_service().raise_alert(
                    f"UDC moved on to puck {self._new_container} on {beamline}",
                    f"Hyperion finished container {current_container} and moved on to {self._new_container}",
                    {
                        Metadata.SAMPLE_ID: str(self._sample_id),
                        Metadata.VISIT: self._visit or "",
                        Metadata.CONTAINER: str(self._new_container),
                    },
                )
        return doc

    def activity_gated_start(self, doc: RunStart):
        if not self._sample_id:
            ISPYB_ZOCALO_CALLBACK_LOGGER.info("Capturing container info for alerts")
            metadata = doc.get("metadata", {})
            self._new_container = metadata.get("container")
            self._sample_id = metadata.get("sample_id")
            self._visit = metadata.get("visit")

    def activity_gated_stop(self, doc: RunStop):
        if not self.active:
            ISPYB_ZOCALO_CALLBACK_LOGGER.info("Resetting state")
            self._new_container = None
            self._sample_id = None
            self._visit = None
