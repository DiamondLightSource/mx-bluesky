import dataclasses
from abc import ABC
from collections.abc import Generator
from datetime import time
from typing import Any

import bluesky.plan_stubs as bps
from bluesky import Msg
from bluesky.protocols import Readable, Reading
from event_model import DataKey, Event, EventDescriptor, RunStart

from mx_bluesky.hyperion.external_interaction.callbacks.plan_reactive_callback import (
    PlanReactiveCallback,
)
from mx_bluesky.hyperion.log import ISPYB_LOGGER
from mx_bluesky.hyperion.parameters.constants import CONST


@dataclasses.dataclass
class AbstractEvent(Readable, ABC):
    def _reading_from_value(self, value):
        return Reading(timestamp=time.time(), value=value)

    def read(self) -> dict[str, Reading]:
        return {f.name: getattr(self, f.name) for f in dataclasses.fields(self)}

    def describe(self) -> dict[str, DataKey]:
        return {
            f.name: DataKey(dtype=f.type, shape=[], source="")
            for f in dataclasses.fields(self)
        }

    @property
    def name(self) -> str:
        return type(self).__name__


@dataclasses.dataclass
class ExceptionEvent(AbstractEvent):
    exception_type: str


def exception_interceptor(exception: Exception) -> Generator[Msg, Any, Any]:
    yield from bps.create(CONST.DESCRIPTORS.SAMPLE_HANDLING_EXCEPTION)
    event = ExceptionEvent(exception_type=exception.__class__.__name__)
    yield from bps.read(event)
    yield from bps.save()


class SampleHandlingCallback(PlanReactiveCallback):
    def __init__(self):
        super().__init__(log=ISPYB_LOGGER)
        self._sample_id: int | None = None
        self._descriptor: str | None = None

    def activity_gated_start(self, doc: RunStart):
        if not self._sample_id:
            self._sample_id = doc["metadata"]["sample_id"]

    def activity_gated_descriptor(self, doc: EventDescriptor) -> EventDescriptor | None:
        if doc["name"] == CONST.DESCRIPTORS.SAMPLE_HANDLING_EXCEPTION:
            self._descriptor = doc["uid"]
        return super().activity_gated_descriptor(doc)

    def activity_gated_event(self, doc: Event) -> Event | None:
        if doc["descriptor"] == self._descriptor:
            exception_type = doc["data"]["exception_type"]
            self._record_exception(exception_type)
        return doc

    def _record_exception(self, exception_type: str):
        # TODO
        pass
