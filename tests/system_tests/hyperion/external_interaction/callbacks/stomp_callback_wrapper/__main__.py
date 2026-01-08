from unittest.mock import patch

from bluesky.callbacks import CallbackBase
from bluesky_stomp.models import MessageTopic
from event_model import Event, RunStart, RunStop

from mx_bluesky.hyperion.external_interaction.callbacks.__main__ import (
    StompDispatcherContextMgr,
    main,
)
from mx_bluesky.hyperion.parameters.cli import CallbackArgs

CALLBACK_TOPIC = "callback_test_events"


class PatchedStompCallbackMgr(StompDispatcherContextMgr):
    def __init__(self, args: CallbackArgs, callbacks: list[CallbackBase]) -> None:
        super().__init__(args, callbacks)
        callback = callbacks[0]
        assert isinstance(callback, StompTestCallback)
        self.callback = callback

    def __enter__(self):
        super().__enter__()
        self.callback.init(self._stomp_client)
        return self


class StompTestCallback(CallbackBase):
    def __init__(self) -> None:
        super().__init__()
        self.stomp_client = None
        self.destination = MessageTopic(name=CALLBACK_TOPIC)

    def init(self, stomp_client):
        self.stomp_client = stomp_client
        self.fire_event_back("init")

    def start(self, doc: RunStart) -> RunStart | None:
        self.fire_event_back(f"start: {doc['run_name']}")  # type: ignore
        return super().start(doc)

    def stop(self, doc: RunStop) -> RunStop | None:
        self.fire_event_back("stop")
        return super().stop(doc)

    def event(self, doc: Event) -> Event:
        self.fire_event_back(f"event: {doc['data']['baton-requested_user']}")
        return super().event(doc)

    def fire_event_back(self, msg: str):
        self.stomp_client.send(destination=self.destination, obj=msg)  # type: ignore


if __name__ == "__main__":

    def mock_setup_callbacks():
        return [StompTestCallback()]

    with (
        patch(
            "mx_bluesky.hyperion.external_interaction.callbacks.__main__.setup_callbacks",
            return_value=mock_setup_callbacks(),
        ),
        patch(
            "mx_bluesky.hyperion.external_interaction.callbacks.__main__.StompDispatcherContextMgr",
            PatchedStompCallbackMgr,
        ),
    ):
        main()
