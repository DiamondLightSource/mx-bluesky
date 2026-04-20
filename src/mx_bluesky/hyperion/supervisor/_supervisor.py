import time
from collections.abc import Sequence

from blueapi.client.client import BlueapiClient
from blueapi.client.event_bus import BlueskyStreamingError
from blueapi.client.rest import ServiceUnavailableError
from blueapi.config import ApplicationConfig
from blueapi.core import BlueskyContext
from blueapi.service.model import TaskRequest
from blueapi.worker.event import TaskError
from bluesky import plan_stubs as bps
from bluesky.utils import MsgGenerator
from pydantic import BaseModel

from mx_bluesky.common.external_interaction.alerting import get_alerting_service
from mx_bluesky.common.parameters.constants import Status
from mx_bluesky.common.utils.exceptions import CrystalNotFoundError, SampleError
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.hyperion._plan_runner_params import (
    RobotUnload,
    UDCCleanup,
    UDCDefaultState,
    Wait,
)
from mx_bluesky.hyperion.blueapi.parameters import LoadCentreCollectParams
from mx_bluesky.hyperion.plan_runner import PlanError, PlanRunner
from mx_bluesky.hyperion.supervisor._task_monitor import TaskMonitor

MAX_TRIES = 3
RETRY_INITIAL_DELAY_S = 2


class SupervisorRunner(PlanRunner):
    """Runner that executes plans by delegating to a remote blueapi instance"""

    def __init__(
        self,
        bluesky_context: BlueskyContext,
        client_config: ApplicationConfig,
        dev_mode: bool,
    ):
        super().__init__(bluesky_context, dev_mode)
        self.blueapi_client = BlueapiClient.from_config(client_config)
        self._current_status = Status.IDLE

    def decode_and_execute(
        self, current_visit: str | None, parameter_list: Sequence[BaseModel]
    ) -> MsgGenerator:
        try:
            yield from self.check_external_callbacks_are_alive()
        except Exception as e:
            raise PlanError(f"Exception raised during plan execution: {e}") from e
        instrument_session = current_visit or "NO_VISIT"
        try:
            if self._current_status == Status.ABORTING:
                raise PlanError("Plan execution cancelled, supervisor is shutting down")
            self._current_status = Status.BUSY
            try:
                for parameters in parameter_list:
                    LOGGER.info(
                        f"Executing plan with parameters: {parameters.model_dump_json(indent=2)}"
                    )
                    match parameters:
                        case LoadCentreCollectParams():
                            task_request = TaskRequest(
                                name="load_centre_collect",
                                params={"parameters": parameters},
                                instrument_session=instrument_session,
                            )
                            self._run_task_remotely(task_request)
                        case RobotUnload():
                            task_request = TaskRequest(
                                name="robot_unload",
                                params={"visit": current_visit},
                                instrument_session=instrument_session,
                            )
                            self._run_task_remotely(task_request)
                        case Wait():
                            yield from bps.sleep(parameters.duration_s)
                        case UDCDefaultState():
                            task_request = TaskRequest(
                                name="move_to_udc_default_state",
                                params={},
                                instrument_session=instrument_session,
                            )
                            self._run_task_remotely(task_request)
                        case UDCCleanup():
                            task_request = TaskRequest(
                                name="clean_up_udc",
                                params={},
                                instrument_session=instrument_session,
                            )
                            self._run_task_remotely(task_request)
                        case _:
                            raise AssertionError(
                                f"Unsupported instruction decoded from agamemnon {type(parameters)}"
                            )
            except SampleError:
                LOGGER.info("Ignoring sample error, continuing...")
        except:
            self._current_status = Status.FAILED
            raise
        else:
            self._current_status = Status.IDLE
        return current_visit

    @property
    def current_status(self) -> Status:
        return self._current_status

    def is_connected(self) -> bool:
        try:
            self.blueapi_client.state  # noqa: B018
        except Exception as e:
            LOGGER.debug(f"Failed to get worker state: {e}")
            return False
        return True

    def shutdown(self):
        LOGGER.info(
            "Hyperion supervisor received shutdown request, signalling abort to BlueAPI server..."
        )
        if self.current_status != Status.BUSY:
            self.request_run_engine_abort()
        else:
            self._current_status = Status.ABORTING
            self.blueapi_client.abort()

    def _run_task_remotely(self, task_request: TaskRequest):
        try:
            with TaskMonitor(self.blueapi_client, task_request) as task_monitor:
                tries, task_status, delay = MAX_TRIES, None, RETRY_INITIAL_DELAY_S
                while tries > 0:
                    tries -= 1
                    try:
                        task_status = self.blueapi_client.run_task(
                            task_request, on_event=task_monitor.on_blueapi_event
                        )
                        break
                    except ServiceUnavailableError as e:
                        LOGGER.warning(
                            "Could not connect to blueapi client.", exc_info=e
                        )
                        time.sleep(delay)  # noqa
                        delay += delay
                    except BlueskyStreamingError:
                        raise
                    except Exception as e:
                        get_alerting_service().raise_error_alert(
                            "Unexpected error communicating with hyperion-blueapi", {}
                        )
                        raise PlanError(
                            "Unexpected error communicating with hyperion-blueapi"
                        ) from e
                else:
                    LOGGER.error("Max retries reached, ending UDC.")
                    get_alerting_service().raise_error_alert(
                        "hyperion-supervisor stopped UDC because unable to connect to hyperion-blueapi.",
                        {},
                    )
                    raise PlanError(
                        f"Unable to connect to hyperion-blueapi after {MAX_TRIES} attempts, ending UDC"
                    )
            LOGGER.info(
                f"hyperion-blueapi completed task execution with task_status {task_status}"
            )

            match task_status.result:
                case TaskError() as task_error:
                    LOGGER.info(
                        f"hyperion-blueapi plan execution encountered an error: {task_error.type}: {task_error.message}"
                    )
                    match task_error.type:
                        case CrystalNotFoundError.__name__ | SampleError.__name__:
                            raise SampleError(
                                f"Remote task error: {task_error.message}"
                            )
                        case _:
                            if self.current_status != Status.ABORTING:
                                raise PlanError(
                                    f"Exception raised during plan execution: {task_error}"
                                )
        except BlueskyStreamingError as e:
            if self.current_status != Status.ABORTING:
                raise PlanError(
                    "BlueskyStreamingError raised during plan execution"
                ) from e
        finally:
            if self.current_status == Status.ABORTING:
                LOGGER.info("Aborting local runner...")
                self.request_run_engine_abort()
