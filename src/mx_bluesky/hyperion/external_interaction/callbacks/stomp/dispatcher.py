from blueapi.client.event_bus import AnyEvent
from blueapi.core import DataEvent
from bluesky.run_engine import Dispatcher
from bluesky_stomp.messaging import MessageContext, StompClient
from bluesky_stomp.models import MessageTopic
from event_model import DocumentNames

from mx_bluesky.common.utils.log import ISPYB_ZOCALO_CALLBACK_LOGGER as LOGGER

BLUEAPI_EVENT_TOPIC = "public.worker.event"


class StompDispatcher(Dispatcher):
    def __init__(self, stomp_client: StompClient):
        super().__init__()
        self._client = stomp_client

    def __enter__(self):
        self._subscription_id = self._client.subscribe(
            MessageTopic(name=BLUEAPI_EVENT_TOPIC), self._on_event
        )
        LOGGER.info("Connecting to stomp broker...")
        self._client.connect()

    def __exit__(self, exc_type, exc_val, exc_tb):
        LOGGER.info("Disconnecting from stomp and unsubscribing...")
        self._client.disconnect()
        self._client.unsubscribe(self._subscription_id)

    def _on_event(self, event: AnyEvent, context: MessageContext):
        match event:
            case DataEvent(name=name, doc=doc):  # type: ignore
                self.process(DocumentNames[name], doc)
