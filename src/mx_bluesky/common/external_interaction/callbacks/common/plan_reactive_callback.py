from __future__ import annotations

from collections.abc import Callable
from logging import Logger
from typing import TYPE_CHECKING, Any

from bluesky.callbacks import CallbackBase

if TYPE_CHECKING:
    from event_model.documents import Event, EventDescriptor, RunStart, RunStop


class PlanReactiveCallback(CallbackBase):
    log: Logger  # type: ignore # this is initialised to None and not annotated in the superclass

    def __init__(
        self,
        log: Logger,
        *,
        emit: Callable[..., Any] | None = None,
    ) -> None:
        """A callback base class which can be left permanently subscribed to a plan, and
        will 'activate' and 'deactivate' at the start and end of a plan which provides
        metadata to trigger this.
        The run_decorator of the plan should include in its metadata dictionary the key
        'activate callbacks', with a list of strings of the callback class(es) to
        activate or deactivate. On a recieving a start doc which specifies this, this
        class will be activated, and on recieving the stop document for the
        corresponding uid it will deactivate. The ordinary 'start', 'descriptor',
        'event' and 'stop' methods will be triggered as normal, and will in turn trigger
        'activity_gated_' methods - to preserve this functionality, subclasses which
        override 'start' etc. should include a call to super().start(...) etc.
        The logic of how activation is triggered will change to a more readable, version
        in the future (https://github.com/DiamondLightSource/hyperion/issues/964)."""

        super().__init__(emit=emit)
        self.emit_cb = emit  # to avoid GC; base class only holds a WeakRef
        self.active = False
        self.activity_uid = ""
        self.log = log

    def _run_activity_gated(self, name: str, func, doc, override=False):
        # Runs `func` if self.active is True or overide is true. Override can be used
        # to run the function even after setting self.active to False, i.e. in the last
        # handler of a run.

        running_gated_function = override or self.active
        if not running_gated_function:
            return doc
        try:
            return self.emit(name, func(doc))
        except Exception as e:
            self.log.exception(e)
            raise

    def start(self, doc: RunStart) -> RunStart | None:
        callbacks_to_activate = doc.get("activate_callbacks")
        if callbacks_to_activate and not self.active:
            activate = type(self).__name__ in callbacks_to_activate
            self.active = activate
            self.log.info(
                f"{'' if activate else 'not'} activating {type(self).__name__}"
            )
            self.activity_uid = doc.get("uid")
        return self._run_activity_gated("start", self.activity_gated_start, doc)

    def descriptor(self, doc: EventDescriptor) -> EventDescriptor | None:
        return self._run_activity_gated(
            "descriptor", self.activity_gated_descriptor, doc
        )

    def event(self, doc: Event) -> Event | None:  # type: ignore
        return self._run_activity_gated("event", self.activity_gated_event, doc)

    def stop(self, doc: RunStop) -> RunStop | None:
        do_stop = self.active
        if doc.get("run_start") == self.activity_uid:
            self.active = False
            self.activity_uid = ""
        return (
            self._run_activity_gated(
                "stop", self.activity_gated_stop, doc, override=True
            )
            if do_stop
            else doc
        )

    def activity_gated_start(self, doc: RunStart) -> RunStart | None:
        return doc

    def activity_gated_descriptor(self, doc: EventDescriptor) -> EventDescriptor | None:
        return doc

    def activity_gated_event(self, doc: Event) -> Event | None:
        return doc

    def activity_gated_stop(self, doc: RunStop) -> RunStop | None:
        return doc

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} with id: {hex(id(self))} - active: {self.active}>"
