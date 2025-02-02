from bluesky.callbacks import CallbackBase
from event_model.documents.run_start import RunStart

from mx_bluesky.common.utils.log import LOGGER

from .logging_callback import format_doc_for_log


class ApertureChangeCallback(CallbackBase):
    """A callback that's used to send the selected aperture back to GDA"""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.last_selected_aperture: str = "NONE"

    def start(self, doc: RunStart):
        if doc.get("subplan_name") == "change_aperture":
            LOGGER.debug(f"START: {format_doc_for_log(doc)}")
            ap_size = doc.get("aperture_size")
            assert isinstance(ap_size, str)
            LOGGER.info(f"Updating most recent in-plan aperture change to {ap_size}.")
            self.last_selected_aperture = ap_size
