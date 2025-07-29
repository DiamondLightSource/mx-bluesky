import threading
from collections.abc import Callable
from typing import Any

from blueapi.core import BlueskyContext
from bluesky.utils import MsgGenerator, RequestAbort

from mx_bluesky.common.parameters.components import MxBlueskyParameters
from mx_bluesky.common.parameters.constants import Status
from mx_bluesky.common.utils.exceptions import WarningException
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.hyperion.experiment_plans.experiment_registry import PLAN_REGISTRY
from mx_bluesky.hyperion.runner import BaseRunner


class PlanException(Exception):
    """Identifies an exception that was encountered during plan execution."""

    pass


class PlanRunner(BaseRunner):
    """Runner that executes experiments from inside a running Bluesky plan"""

    def __init__(
        self,
        context: BlueskyContext,
    ) -> None:
        super().__init__(context)
        self.current_status: Status = Status.IDLE
        self._last_run_aborted: bool = False

    def execute_plan(
        self,
        experiment: Callable,
        parameters: MxBlueskyParameters,
        plan_name: str | None = None,
    ) -> MsgGenerator:
        """Execute the specified experiment plan.
        Args:
            experiment: The experiment to run
            parameters: The parameters for the experiment
            plan_name: Name of the plan to find in the registry, if it requires devices to be located.
        Raises:
            PlanException: If the plan raised an exception
            RequestAbort: If the RunEngine aborted during execution"""
        LOGGER.info(
            f"Executing plan with parameters: {parameters.model_dump_json(indent=2)}"
        )

        devices: Any = (
            PLAN_REGISTRY[plan_name]["setup"](self.context) if plan_name else None
        )

        if self.current_status == Status.ABORTING:
            return

        self.current_status = Status.BUSY

        try:
            yield from experiment(parameters, devices)
            self.current_status = Status.IDLE
        except WarningException as e:
            LOGGER.warning("Plan failed with warning", exc_info=e)
            self.current_status = Status.FAILED
        except RequestAbort:
            # This will occur when the run engine processes an abort when we shut down
            LOGGER.info("UDC Runner aborting")
            raise
        except Exception as e:
            LOGGER.error("Plan failed with exception", exc_info=e)
            self.current_status = Status.FAILED
            raise PlanException("Exception thrown in plan execution") from e

    def shutdown(self):
        """Performs a prompt shutdown. Aborts the run engine and terminates the loop
        waiting for messages."""

        def issue_abort():
            try:
                # abort() causes the run engine to throw a RequestAbort exception
                # inside the plan, which will propagate through the contingency wrappers.
                # When the plan returns, the run engine will raise RunEngineInterrupted
                self.RE.abort()
            except Exception as e:
                LOGGER.warning(
                    "Exception encountered when issuing abort() to RunEngine:",
                    exc_info=e,
                )

        print("Received shutdown")
        LOGGER.info("Shutting down: Stopping the run engine gracefully")
        if self.current_status != Status.ABORTING:
            self.current_status = Status.ABORTING
            self._last_run_aborted = True
            stopping_thread = threading.Thread(target=issue_abort)
            stopping_thread.start()
            return
