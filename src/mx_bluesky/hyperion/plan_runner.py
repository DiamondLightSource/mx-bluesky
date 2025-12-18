import threading
import time
from abc import abstractmethod
from collections.abc import Sequence

from blueapi.core import BlueskyContext
from bluesky import plan_stubs as bps
from bluesky.utils import MsgGenerator

from mx_bluesky.common.parameters.components import MxBlueskyParameters
from mx_bluesky.common.parameters.constants import Status
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.hyperion.runner import BaseRunner


class PlanError(Exception):
    """Identifies an exception that was encountered during plan execution."""

    pass


class PlanRunner(BaseRunner):
    EXTERNAL_CALLBACK_POLL_INTERVAL_S = 1
    EXTERNAL_CALLBACK_WATCHDOG_TIMER_S = 60

    def __init__(self, context: BlueskyContext, dev_mode: bool):
        super().__init__(context)
        self._callbacks_started = False
        self._callback_watchdog_expiry = time.monotonic()
        self.is_dev_mode = dev_mode

    @abstractmethod
    def decode_and_execute(
        self, current_visit: str | None, parameter_list: Sequence[MxBlueskyParameters]
    ) -> MsgGenerator:
        pass

    def reset_callback_watchdog_timer(self):
        """Called periodically to reset the watchdog timer when the external callbacks ping us."""
        self._callbacks_started = True
        self._callback_watchdog_expiry = (
            time.monotonic() + self.EXTERNAL_CALLBACK_WATCHDOG_TIMER_S
        )

    @property
    @abstractmethod
    def current_status(self) -> Status:
        pass

    def check_external_callbacks_are_alive(self):
        callback_expiry = time.monotonic() + self.EXTERNAL_CALLBACK_WATCHDOG_TIMER_S
        while time.monotonic() < callback_expiry:
            if self._callbacks_started:
                break
            # If on first launch the external callbacks aren't started yet, wait until they are
            LOGGER.info("Waiting for external callbacks to start")
            yield from bps.sleep(self.EXTERNAL_CALLBACK_POLL_INTERVAL_S)
        else:
            raise RuntimeError("External callbacks not running - try restarting")

        if not self._external_callbacks_are_alive():
            raise RuntimeError(
                "External callback watchdog timer expired, check external callbacks are running."
            )

    def request_run_engine_abort(self):
        """Asynchronously request an abort from the run engine. This cannot be done from
        inside the main thread."""

        def issue_abort():
            try:
                # abort() causes the run engine to throw a RequestAbort exception
                # inside the plan, which will propagate through the contingency wrappers.
                # When the plan returns, the run engine will raise RunEngineInterrupted
                self.run_engine.abort()
            except Exception as e:
                LOGGER.warning(
                    "Exception encountered when issuing abort() to RunEngine:",
                    exc_info=e,
                )

        stopping_thread = threading.Thread(target=issue_abort)
        stopping_thread.start()

    def _external_callbacks_are_alive(self) -> bool:
        return time.monotonic() < self._callback_watchdog_expiry
