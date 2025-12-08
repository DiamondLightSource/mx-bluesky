import threading
import time
from collections.abc import Callable

from blueapi.core import BlueskyContext
from bluesky import plan_stubs as bps
from bluesky.utils import MsgGenerator, RequestAbort

from mx_bluesky.common.parameters.constants import Status
from mx_bluesky.common.utils.exceptions import WarningError
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.hyperion.runner import BaseRunner


class PlanError(Exception):
    """Identifies an exception that was encountered during plan execution."""

    pass


class PlanRunner(BaseRunner):
    """Runner that executes experiments from inside a running Bluesky plan"""

    EXTERNAL_CALLBACK_WATCHDOG_TIMER_S = 60
    EXTERNAL_CALLBACK_POLL_INTERVAL_S = 1

    def __init__(self, context: BlueskyContext, dev_mode: bool) -> None:
        super().__init__(context)
        self.current_status: Status = Status.IDLE
        self.is_dev_mode = dev_mode
        self._callbacks_started = False
        self._callback_watchdog_expiry = time.monotonic()

    def execute_plan(
        self,
        experiment: Callable[[], MsgGenerator],
    ) -> MsgGenerator:
        """Execute the specified experiment plan.
        Args:
            experiment: The experiment to run
        Raises:
            PlanError: If the plan raised an exception
            RequestAbort: If the RunEngine aborted during execution"""

        self.current_status = Status.BUSY

        try:
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
            yield from experiment()
            self.current_status = Status.IDLE
        except WarningError as e:
            LOGGER.warning("Plan failed with warning", exc_info=e)
            self.current_status = Status.FAILED
        except RequestAbort:
            # This will occur when the run engine processes an abort when we shut down
            LOGGER.info("UDC Runner aborting")
            raise
        except Exception as e:
            LOGGER.error("Plan failed with exception", exc_info=e)
            self.current_status = Status.FAILED
            raise PlanError("Exception thrown in plan execution") from e

    def shutdown(self):
        """Performs a prompt shutdown. Aborts the run engine and terminates the loop
        waiting for messages."""

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

        LOGGER.info("Shutting down: Stopping the run engine gracefully")
        if self.current_status != Status.ABORTING:
            self.current_status = Status.ABORTING
            stopping_thread = threading.Thread(target=issue_abort)
            stopping_thread.start()
            return

    def reset_callback_watchdog_timer(self):
        """Called periodically to reset the watchdog timer when the external callbacks ping us."""
        self._callbacks_started = True
        self._callback_watchdog_expiry = (
            time.monotonic() + self.EXTERNAL_CALLBACK_WATCHDOG_TIMER_S
        )

    def _external_callbacks_are_alive(self) -> bool:
        return time.monotonic() < self._callback_watchdog_expiry
