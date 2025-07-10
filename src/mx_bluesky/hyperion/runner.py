import threading
from abc import abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from queue import Empty, Queue
from typing import Any

from blueapi.core import BlueskyContext
from bluesky.callbacks.zmq import Publisher
from bluesky.utils import MsgGenerator

from mx_bluesky.common.external_interaction.callbacks.common.log_uid_tag_callback import (
    LogUidTaggingCallback,
)
from mx_bluesky.common.parameters.components import MxBlueskyParameters
from mx_bluesky.common.parameters.constants import Actions, Status
from mx_bluesky.common.utils.exceptions import WarningException
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.common.utils.tracing import TRACER
from mx_bluesky.hyperion.experiment_plans.experiment_registry import PLAN_REGISTRY
from mx_bluesky.hyperion.parameters.constants import CONST


@dataclass
class Command:
    action: Actions
    devices: Any | None = None
    experiment: Callable[[Any, Any], MsgGenerator] | None = None

    def __str__(self):
        return f"Command({self.action}, {self.parameters}"

    parameters: MxBlueskyParameters | None = None


@dataclass
class StatusAndMessage:
    status: str
    message: str = ""

    def __init__(self, status: Status, message: str = "") -> None:
        self.status = status.value
        self.message = message


@dataclass
class ErrorStatusAndMessage(StatusAndMessage):
    exception_type: str = ""


def make_error_status_and_message(exception: Exception):
    return ErrorStatusAndMessage(
        status=Status.FAILED.value,
        message=repr(exception),
        exception_type=type(exception).__name__,
    )


class BlueskyRunner:
    def __init__(
        self,
        context: BlueskyContext,
    ) -> None:
        self.current_status: StatusAndMessage = StatusAndMessage(Status.IDLE)
        self.context: BlueskyContext = context
        self.RE = context.run_engine

        self._last_run_aborted: bool = False
        self._command_queue: Queue[Command] = Queue()
        self._logging_uid_tag_callback = LogUidTaggingCallback()
        LOGGER.info("Connecting to external callback ZMQ proxy...")
        self._publisher = Publisher(f"localhost:{CONST.CALLBACK_0MQ_PROXY_PORTS[0]}")

        self.RE.subscribe(self._logging_uid_tag_callback)
        self.RE.subscribe(self._publisher)

    def start(
        self,
        experiment: Callable,
        parameters: MxBlueskyParameters,
        plan_name: str | None = None,
    ) -> StatusAndMessage:
        """Start a new bluesky plan
        Args:
            experiment: A bluesky plan
            parameters: The parameters to be submitted
            plan_name: Name of the plan that will be used to resolve the composite factory
                to supply devices for the plan, if any are needed"""
        LOGGER.info(f"Started with parameters: {parameters.model_dump_json(indent=2)}")

        devices: Any = (
            PLAN_REGISTRY[plan_name]["setup"](self.context) if plan_name else None
        )

        if (
            self.current_status.status == Status.BUSY.value
            or self.current_status.status == Status.ABORTING.value
        ):
            return StatusAndMessage(Status.FAILED, "Bluesky already running")
        else:
            self.current_status = StatusAndMessage(Status.BUSY)
            self._command_queue.put(
                Command(
                    action=Actions.START,
                    devices=devices,
                    experiment=experiment,
                    parameters=parameters,
                )
            )
            return StatusAndMessage(Status.SUCCESS)

    def stop(self) -> StatusAndMessage:
        """Stop the currently executing plan."""
        if self.current_status.status == Status.IDLE.value:
            return StatusAndMessage(Status.FAILED, "Bluesky not running")
        elif self.current_status.status == Status.ABORTING.value:
            return StatusAndMessage(Status.FAILED, "Bluesky already stopping")
        else:
            self.current_status = StatusAndMessage(Status.ABORTING)
            stopping_thread = threading.Thread(target=self._stopping_thread)
            stopping_thread.start()
            self._last_run_aborted = True
            return StatusAndMessage(Status.ABORTING)

    def shutdown(self):
        """Stops the run engine and the loop waiting for messages."""
        print("Shutting down: Stopping the run engine gracefully")
        self.stop()
        self._command_queue.put(Command(action=Actions.SHUTDOWN))

    @abstractmethod
    def wait_on_queue(self):
        """Entry point to the processing loop"""
        pass

    def _stopping_thread(self):
        try:
            # abort() causes the run engine to throw a RequestAbort exception
            # inside the plan, which will propagate through the contingency wrappers.
            # When the plan returns, the run engine will raise RunEngineInterrupted
            self.RE.abort()
            self.current_status = StatusAndMessage(Status.IDLE)
        except Exception as e:
            self.current_status = make_error_status_and_message(e)

    def fetch_next_command(self, block: bool = True) -> Command | None:
        """Fetch the next command from the queue
        Args:
            block: True to block if no command is in the queue, False to return None instead
        """
        try:
            return self._command_queue.get(block=block)
        except Empty:
            return None


class GDARunner(BlueskyRunner):
    """Runner that executes plans submitted by Flask requests from GDA."""

    def wait_on_queue(self):
        while True:
            command = self.fetch_next_command()
            if command.action == Actions.SHUTDOWN:
                return
            elif command.action == Actions.START:
                if command.experiment is None:
                    raise ValueError("No experiment provided for START")
                try:
                    with TRACER.start_span("do_run"):
                        self.RE(command.experiment(command.devices, command.parameters))

                    self.current_status = StatusAndMessage(Status.IDLE)

                    self._last_run_aborted = False
                except WarningException as exception:
                    LOGGER.warning("Warning Exception", exc_info=True)
                    self.current_status = make_error_status_and_message(exception)
                except Exception as exception:
                    LOGGER.error("Exception on running plan", exc_info=True)

                    if self._last_run_aborted:
                        # Aborting will cause an exception here that we want to swallow
                        self._last_run_aborted = False
                    else:
                        self.current_status = make_error_status_and_message(exception)
