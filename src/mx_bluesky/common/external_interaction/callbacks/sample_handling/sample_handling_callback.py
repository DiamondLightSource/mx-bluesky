from event_model import RunStart, RunStop

from mx_bluesky.common.external_interaction.callbacks.common.plan_reactive_callback import (
    PlanReactiveCallback,
)
from mx_bluesky.common.external_interaction.ispyb.exp_eye_store import (
    BLSampleStatus,
    ExpeyeInteraction,
)
from mx_bluesky.common.utils.exceptions import CrystalNotFoundException, SampleException
from mx_bluesky.common.utils.log import ISPYB_ZOCALO_CALLBACK_LOGGER


class SampleHandlingCallback(PlanReactiveCallback):
    """Intercepts exceptions from experiment plans and updates the ISPyB BLSampleStatus
    field according to the type of exception raised."""

    def __init__(self, record_loaded_on_success=False):
        super().__init__(log=ISPYB_ZOCALO_CALLBACK_LOGGER)
        self._sample_id: int | None = None
        self._descriptor: str | None = None
        self._run_id: str | None = None

        # Record 'sample loaded' if document successfully stops
        self.record_loaded_on_success = record_loaded_on_success

    def activity_gated_start(self, doc: RunStart):
        if not self._sample_id and self.active:
            sample_id = doc.get("metadata", {}).get("sample_id")
            self.log.info(f"Recording sample ID at run start {sample_id}")
            self._sample_id = sample_id
            self._run_id = self.activity_uid

    def activity_gated_stop(self, doc: RunStop) -> RunStop:
        if self._run_id == doc.get("run_start"):
            expeye = ExpeyeInteraction()
            if doc["exit_status"] != "success":
                exception_type, message = SampleException.type_and_message_from_reason(
                    doc.get("reason", "")
                )
                self.log.info(
                    f"Sample handling callback intercepted exception of type {exception_type}: {message}"
                )
                self._record_exception(exception_type, expeye)

            elif self.record_loaded_on_success:
                self._record_loaded(expeye)

            self._sample_id = None
            self._run_id = None

        return doc

    def _record_exception(self, exception_type: str, expeye: ExpeyeInteraction):
        assert self._sample_id, "Unable to record exception due to no sample ID"
        sample_status = self._decode_sample_status(exception_type)
        expeye.update_sample_status(self._sample_id, sample_status)

    def _decode_sample_status(self, exception_type: str) -> BLSampleStatus:
        match exception_type:
            case SampleException.__name__ | CrystalNotFoundException.__name__:
                return BLSampleStatus.ERROR_SAMPLE
        return BLSampleStatus.ERROR_BEAMLINE

    def _record_loaded(self, expeye: ExpeyeInteraction):
        assert self._sample_id, "Unable to record loaded state due to no sample ID"
        expeye.update_sample_status(self._sample_id, BLSampleStatus.LOADED)
