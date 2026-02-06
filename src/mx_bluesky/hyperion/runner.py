from abc import abstractmethod

from blueapi.core import BlueskyContext
from bluesky.callbacks.zmq import Publisher

from mx_bluesky.common.external_interaction.callbacks.common.log_uid_tag_callback import (
    LogUidTaggingCallback,
)
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.hyperion.parameters.constants import CONST


class BaseRunner:
    @abstractmethod
    def shutdown(self):
        """Performs orderly prompt shutdown.
        Aborts the run engine and terminates the loop waiting for messages."""
        pass

    def __init__(self, context: BlueskyContext):
        self.context: BlueskyContext = context
        self.run_engine = context.run_engine
        # These references are necessary to maintain liveness of callbacks because run_engine
        # only keeps a weakref
        self._logging_uid_tag_callback = LogUidTaggingCallback()
        self._publisher = Publisher(f"localhost:{CONST.CALLBACK_0MQ_PROXY_PORTS[0]}")

        self.run_engine.subscribe(self._logging_uid_tag_callback)
        LOGGER.info("Connecting to external callback ZMQ proxy...")
        self.run_engine.subscribe(self._publisher)
