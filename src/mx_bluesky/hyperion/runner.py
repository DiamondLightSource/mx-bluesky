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
from mx_bluesky.common.utils.exceptions import WarningError
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


class GDARunner(BaseRunner):
    """Runner that executes plans submitted by Flask requests from GDA."""

    def __init__(
        self,
        context: BlueskyContext,
    ) -> None:
        super().__init__(context)
        self.current_status: StatusAndMessage = StatusAndMessage(Status.IDLE)
        self._last_run_aborted: bool = False
        self._command_queue: Queue[Command] = Queue()

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
        if self.current_status.status == Status.ABORTING.value:
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

    def _stopping_thread(self):
        try:
            # abort() causes the run engine to throw a RequestAbort exception
            # inside the plan, which will propagate through the contingency wrappers.
            # When the plan returns, the run engine will raise RunEngineInterrupted
            self.run_engine.abort()
            self.current_status = StatusAndMessage(Status.IDLE)
        except Exception as e:
            self.current_status = make_error_status_and_message(e)

    def fetch_next_command(self) -> Command:
        """Fetch the next command from the queue, blocks if queue is empty."""
        return self._command_queue.get()

    def try_fetch_next_command(self) -> Command | None:
        """Fetch the next command from the queue or return None if no command available."""
        try:
            return self._command_queue.get(block=False)
        except Empty:
            return None

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
                        self.run_engine(
                            command.experiment(command.devices, command.parameters)
                        )

                    self.current_status = StatusAndMessage(Status.IDLE)

                    self._last_run_aborted = False
                except WarningError as exception:
                    LOGGER.warning("Warning Exception", exc_info=True)
                    self.current_status = make_error_status_and_message(exception)
                except Exception as exception:
                    LOGGER.error("Exception on running plan", exc_info=True)

                    if self._last_run_aborted:
                        # Aborting will cause an exception here that we want to swallow
                        self._last_run_aborted = False
                    else:
                        self.current_status = make_error_status_and_message(exception)
