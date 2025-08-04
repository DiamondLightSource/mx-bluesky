from abc import abstractmethod
from collections.abc import Callable
from enum import Enum


class ExternalCallbackStatus(Enum):
    CALLBACK_CONTACT_LOST = 0
    CALLBACK_RECOVERY = 1
    CALLBACK_ERROR = 2


class MonitoringService:
    """A service for checking on a remote external callback process to check whether it is live."""

    @abstractmethod
    def wait_for_connection(
        self,
        address: str,
        port: int,
        callback: Callable[[ExternalCallbackStatus], None],
    ):
        """Wait for connection to the external callback process, this will
        start a background thread to periodically poll the external process for liveness.
        Args:
            address: Address of the socket to connect to
            port: Port number of the socket to connect to
            callback: a liveness callback to be called in the event that the
            external callback process has changed status."""
        pass
