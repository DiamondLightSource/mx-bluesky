from event_model import RunStop

from mx_bluesky.common.external_interaction.callbacks.sample_handling.sample_handling_callback import (
    SampleHandlingCallback,
)
from mx_bluesky.common.external_interaction.ispyb.exp_eye_store import (
    BLSampleStatus,
)


class SampleLoadedCallback(SampleHandlingCallback):
    """Updates ISPYB sample status with sample loaded on successful document stop, or
    with exception on unsuccessful stop"""

    def activity_gated_stop(self, doc: RunStop) -> RunStop:
        doc = super().activity_gated_stop(doc)
        if self._run_id == doc.get("run_start") and doc["exit_status"] != "success":
            self._record_loaded()
        return doc

    def _record_loaded(self):
        assert self._sample_id, "Unable to record loaded state due to no sample ID"
        self.expeye.update_sample_status(self._sample_id, BLSampleStatus.LOADED)
