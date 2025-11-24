from dodal.utils import get_beamline_name
from event_model import RunStart, RunStop

from mx_bluesky.common.external_interaction.alerting import (
    Metadata,
    get_alerting_service,
)
from mx_bluesky.common.external_interaction.callbacks.common.plan_reactive_callback import (
    PlanReactiveCallback,
)
from mx_bluesky.common.external_interaction.ispyb.exp_eye_store import (
    BLSampleStatus,
    ExpeyeInteraction,
)
from mx_bluesky.common.utils.exceptions import CrystalNotFoundError, SampleError
from mx_bluesky.common.utils.log import ISPYB_ZOCALO_CALLBACK_LOGGER


class SampleHandlingCallback(PlanReactiveCallback):
    """Intercepts exceptions from experiment plans and:
    * Updates the ISPyB BLSampleStatus field according to the type of exception raised.
    * Triggers an alert with details of the error."""

    def __init__(self, record_loaded_on_success=False):
        super().__init__(log=ISPYB_ZOCALO_CALLBACK_LOGGER)
        self._sample_id: int | None = None
        self._visit: str | None = None
        self._descriptor: str | None = None
        self._run_id: str | None = None
        self._container: int | None = None

        # Record 'sample loaded' if document successfully stops
        self.record_loaded_on_success = record_loaded_on_success

    def activity_gated_start(self, doc: RunStart):
        if not self._sample_id and self.active:
            metadata = doc.get("metadata", {})
            sample_id = metadata.get("sample_id")
            self.log.info(f"Recording sample ID at run start {sample_id}")
            self._sample_id = sample_id
            self._visit = metadata.get("visit")
            self._run_id = self.activity_uid
            self._container = metadata.get("container")

    def activity_gated_stop(self, doc: RunStop) -> RunStop:
        if self._run_id == doc.get("run_start"):
            expeye = ExpeyeInteraction()
            if doc["exit_status"] != "success":
                reason = doc.get("reason", "")
                exception_type, message = SampleError.type_and_message_from_reason(
                    reason
                )
                self.log.info(
                    f"Sample handling callback intercepted exception of type {exception_type}: {message}"
                )
                self._record_exception(exception_type, expeye, reason)

            elif self.record_loaded_on_success:
                self._record_loaded(expeye)

            self._sample_id = None
            self._run_id = None

        return doc

    def _record_exception(
        self, exception_type: str, expeye: ExpeyeInteraction, reason: str
    ):
        assert self._sample_id, "Unable to record exception due to no sample ID"
        sample_status = self._decode_sample_status(exception_type)
        expeye.update_sample_status(self._sample_id, sample_status)
        if sample_status == BLSampleStatus.ERROR_BEAMLINE:
            beamline = get_beamline_name("")
            get_alerting_service().raise_alert(
                f"UDC encountered an error on {beamline}",
                f"Hyperion encountered the following beamline error: {reason}",
                {
                    Metadata.SAMPLE_ID: str(self._sample_id),
                    Metadata.VISIT: self._visit or "",
                    Metadata.CONTAINER: str(self._container),
                },
            )

    def _decode_sample_status(self, exception_type: str) -> BLSampleStatus:
        match exception_type:
            case SampleError.__name__ | CrystalNotFoundError.__name__:
                return BLSampleStatus.ERROR_SAMPLE
        return BLSampleStatus.ERROR_BEAMLINE

    def _record_loaded(self, expeye: ExpeyeInteraction):
        assert self._sample_id, "Unable to record loaded state due to no sample ID"
        expeye.update_sample_status(self._sample_id, BLSampleStatus.LOADED)
