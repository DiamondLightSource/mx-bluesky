from __future__ import annotations

from typing import TYPE_CHECKING

from mx_bluesky.common.external_interaction.callbacks.common.ispyb_mapping import (
    get_proposal_and_session_from_visit_string,
)
from mx_bluesky.common.external_interaction.callbacks.common.plan_reactive_callback import (
    PlanReactiveCallback,
)
from mx_bluesky.common.external_interaction.ispyb.exp_eye_store import (
    BLSampleStatus,
    ExpeyeInteraction,
    RobotActionID,
)
from mx_bluesky.common.utils.log import ISPYB_ZOCALO_CALLBACK_LOGGER
from mx_bluesky.hyperion.parameters.constants import CONST

if TYPE_CHECKING:
    from event_model.documents import Event, EventDescriptor, RunStart, RunStop


class RobotLoadISPyBCallback(PlanReactiveCallback):
    def __init__(self) -> None:
        ISPYB_ZOCALO_CALLBACK_LOGGER.debug("Initialising ISPyB Robot Load Callback")
        super().__init__(log=ISPYB_ZOCALO_CALLBACK_LOGGER)
        self._metadata: dict | None = None

        self.run_uid: str | None = None
        self.descriptors: dict[str, EventDescriptor] = {}
        self.action_id: RobotActionID | None = None
        self.expeye = ExpeyeInteraction()

    def activity_gated_start(self, doc: RunStart):
        ISPYB_ZOCALO_CALLBACK_LOGGER.debug(
            "ISPyB robot load callback received start document."
        )
        if doc.get("subplan_name") == CONST.PLAN.ROBOT_LOAD:
            ISPYB_ZOCALO_CALLBACK_LOGGER.debug(
                f"ISPyB robot load callback received: {doc}"
            )
            self.run_uid = doc.get("uid")
            self._metadata = doc.get("metadata")
            assert isinstance(self._metadata, dict)
            proposal, session = get_proposal_and_session_from_visit_string(
                self._metadata["visit"]
            )
            self.action_id = self.expeye.start_load(
                proposal,
                session,
                self._metadata["sample_id"],
                self._metadata["sample_puck"],
                self._metadata["sample_pin"],
            )
        return super().activity_gated_start(doc)

    def activity_gated_descriptor(self, doc: EventDescriptor) -> EventDescriptor | None:
        self.descriptors[doc["uid"]] = doc
        return super().activity_gated_descriptor(doc)

    def activity_gated_event(self, doc: Event) -> Event | None:
        event_descriptor = self.descriptors.get(doc["descriptor"])
        if (
            event_descriptor
            and event_descriptor.get("name") == CONST.DESCRIPTORS.ROBOT_LOAD
        ):
            assert self.action_id is not None, (
                "ISPyB Robot load callback event called unexpectedly"
            )
            barcode = doc["data"]["robot-barcode"]
            oav_snapshot = doc["data"]["oav-snapshot-last_saved_path"]
            webcam_snapshot = doc["data"]["webcam-last_saved_path"]
            # I03 uses webcam/oav snapshots in place of before/after snapshots
            self.expeye.update_barcode_and_snapshots(
                self.action_id, barcode, webcam_snapshot, oav_snapshot
            )

        return super().activity_gated_event(doc)

    def activity_gated_stop(self, doc: RunStop) -> RunStop | None:
        ISPYB_ZOCALO_CALLBACK_LOGGER.debug(
            "ISPyB robot load callback received stop document."
        )
        if doc.get("run_start") == self.run_uid:
            assert self.action_id is not None, (
                "ISPyB Robot load callback stop called unexpectedly"
            )
            exit_status = doc.get("exit_status")
            assert exit_status, "Exit status not available in stop document!"
            assert self._metadata, "Metadata not received before stop document."
            reason = doc.get("reason") or "OK"

            self.expeye.end_load(self.action_id, exit_status, reason)
            self.expeye.update_sample_status(
                self._metadata["sample_id"],
                BLSampleStatus.LOADED
                if exit_status == "success"
                else BLSampleStatus.ERROR_BEAMLINE,
            )
            self.action_id = None
        return super().activity_gated_stop(doc)
