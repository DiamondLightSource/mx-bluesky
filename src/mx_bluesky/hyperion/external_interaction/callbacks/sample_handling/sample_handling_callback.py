from collections.abc import Generator
from typing import Any

from bluesky import Msg
from bluesky.preprocessors import msg_mutator, contingency_wrapper
from bluesky.utils import make_decorator
from event_model import Event, EventDescriptor, RunStart, RunStop

from mx_bluesky.hyperion.external_interaction.callbacks.plan_reactive_callback import (
    PlanReactiveCallback,
)
from mx_bluesky.hyperion.log import ISPYB_LOGGER
from mx_bluesky.hyperion.parameters.constants import CONST


# TODO remove this preprocessor shenanigans once
# https://github.com/bluesky/bluesky/issues/1829 is addressed


def _exception_handling_preprocessor(wrapped_plan: Generator[Msg, Any, Any]):
    """This preprocessor intercepts the enclosing ``close_run`` message and replaces
    the ``reason`` and ``exit_status`` fields if an exception was thrown inside the
    run.
    It is necessary since it is not possible to close a run early because the
    enclosing ``run_decorator`` will still also close the run and checks
    inside ``RunEngine._close_run()`` that will check if there is an imbalance of open/close
    messages."""
    intercepted_exception = None

    def _exception_interceptor(exception: Exception) -> Generator[Msg, Any, Any]:
        nonlocal intercepted_exception
        intercepted_exception = exception
        yield from []

    def close_run_interceptor(msg: Msg) -> Msg:
        if intercepted_exception and msg.command == "close_run":
            msg.kwargs["exit_status"] = "abort"
            msg.kwargs["reason"] = type(intercepted_exception).__name__
        return msg

    plan_with_exception_handler = contingency_wrapper(wrapped_plan, except_plan=_exception_interceptor, auto_raise=True)
    yield from msg_mutator(plan_with_exception_handler, close_run_interceptor)


exception_handling_decorator = make_decorator(_exception_handling_preprocessor)


class SampleHandlingCallback(PlanReactiveCallback):
    def __init__(self):
        super().__init__(log=ISPYB_LOGGER)
        self._sample_id: int | None = None
        self._descriptor: str | None = None

    def activity_gated_start(self, doc: RunStart):
        if not self._sample_id:
            self._sample_id = doc.get("metadata", {}).get("sample_id")

    def activity_gated_descriptor(self, doc: EventDescriptor) -> EventDescriptor | None:
        if doc["name"] == CONST.DESCRIPTORS.SAMPLE_HANDLING_EXCEPTION:
            self._descriptor = doc["uid"]
        return super().activity_gated_descriptor(doc)

    def activity_gated_event(self, doc: Event) -> Event | None:
        if doc["descriptor"] == self._descriptor:
            exception_type = doc["data"]["exception_type"]
            self._record_exception(exception_type)
        return doc

    def activity_gated_stop(self, doc: RunStop) -> RunStop | None:
        if doc["exit_status"] == "abort":
            self._record_exception(doc.get("reason"))
        return super().activity_gated_stop(doc)

    def _record_exception(self, exception_type: str):
        # TODO
        pass
