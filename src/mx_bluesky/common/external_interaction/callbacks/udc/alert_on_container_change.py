from dodal.utils import get_beamline_name
from event_model import RunStart

from mx_bluesky.common.external_interaction.alerting import (
    Metadata,
    get_alerting_service,
)
from mx_bluesky.common.external_interaction.callbacks.common.plan_reactive_callback import (
    PlanReactiveCallback,
)
from mx_bluesky.common.utils.log import ISPYB_ZOCALO_CALLBACK_LOGGER


class AlertOnContainerChange(PlanReactiveCallback):
    """Sends an alert to beamline staff when a pin from a new puck has been loaded.
    This tends to be used as a heartbeat so we know that UDC is running."""

    def __init__(self):
        super().__init__(log=ISPYB_ZOCALO_CALLBACK_LOGGER)
        self._last_container = None

    def activity_gated_start(self, doc: RunStart):
        metadata = doc.get("metadata", {})
        if new_container := metadata.get("container"):
            sample_id = metadata.get("sample_id")
            visit = metadata.get("visit")

            if new_container != self._last_container:
                beamline = get_beamline_name("")
                get_alerting_service().raise_alert(
                    f"UDC moved on to puck {new_container} on {beamline}",
                    f"Hyperion finished container {self._last_container} and moved on to {new_container}",
                    {
                        Metadata.SAMPLE_ID: str(sample_id),
                        Metadata.VISIT: visit or "",
                        Metadata.CONTAINER: str(new_container),
                    },
                )

                self._last_container = new_container
