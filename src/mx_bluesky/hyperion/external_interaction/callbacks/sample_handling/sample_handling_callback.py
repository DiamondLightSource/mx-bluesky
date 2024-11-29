import dataclasses
from collections.abc import Generator
from functools import partial
from typing import Any

import bluesky.plan_stubs as bps
from bluesky.preprocessors import contingency_wrapper
from bluesky.utils import Msg, make_decorator
from event_model import Event, EventDescriptor, RunStart

from mx_bluesky.hyperion.exceptions import CrystalNotFoundException, SampleException
from mx_bluesky.hyperion.external_interaction.callbacks.common.abstract_event import (
    AbstractEvent,
)
from mx_bluesky.hyperion.external_interaction.callbacks.plan_reactive_callback import (
    PlanReactiveCallback,
)
from mx_bluesky.hyperion.external_interaction.ispyb.exp_eye_store import (
    BLSampleStatus,
    ExpeyeInteraction,
)
from mx_bluesky.hyperion.log import ISPYB_LOGGER
from mx_bluesky.hyperion.parameters.constants import CONST

# TODO remove this event-raising shenanigans once
# https://github.com/bluesky/bluesky/issues/1829 is addressed


@dataclasses.dataclass(frozen=True)
class _ExceptionEvent(AbstractEvent):
    exception_type: str


def _exception_interceptor(exception: Exception) -> Generator[Msg, Any, Any]:
    yield from bps.create(CONST.DESCRIPTORS.SAMPLE_HANDLING_EXCEPTION)
    yield from bps.read(_ExceptionEvent(type(exception).__name__))
    yield from bps.save()


sample_handling_callback_decorator = make_decorator(
    partial(contingency_wrapper, except_plan=_exception_interceptor)
)


class SampleHandlingCallback(PlanReactiveCallback):
    """Intercepts exceptions from experiment plans and updates the ISPyB BLSampleStatus
    field according to the type of exception raised."""

    def __init__(self):
        super().__init__(log=ISPYB_LOGGER)
        self._sample_id: int | None = None
        self._descriptor: str | None = None

    def activity_gated_start(self, doc: RunStart):
        if not self._sample_id:
            sample_id = doc.get("metadata", {}).get("sample_id")
            self.log.info(f"Recording sample ID at run start {sample_id}")
            self._sample_id = sample_id

    def activity_gated_descriptor(self, doc: EventDescriptor) -> EventDescriptor | None:
        if doc.get("name") == CONST.DESCRIPTORS.SAMPLE_HANDLING_EXCEPTION:
            self._descriptor = doc["uid"]
        return super().activity_gated_descriptor(doc)

    def activity_gated_event(self, doc: Event) -> Event | None:
        if doc["descriptor"] == self._descriptor:
            exception_type = doc["data"]["exception_type"]
            self.log.info(
                f"Sample handling callback intercepted exception of type {exception_type}"
            )
            self._record_exception(exception_type)
        return doc

    def _record_exception(self, exception_type: str):
        expeye = ExpeyeInteraction()
        assert self._sample_id, "Unable to record exception due to no sample ID"
        sample_status = self._decode_sample_status(exception_type)
        expeye.update_sample_status(self._sample_id, sample_status)

    def _decode_sample_status(self, exception_type: str) -> BLSampleStatus:
        match exception_type:
            case SampleException.__name__ | CrystalNotFoundException.__name__:
                return BLSampleStatus.ERROR_SAMPLE
        return BLSampleStatus.ERROR_BEAMLINE
