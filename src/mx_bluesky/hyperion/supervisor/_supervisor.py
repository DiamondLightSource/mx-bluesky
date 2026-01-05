from collections.abc import Sequence

from blueapi.client.client import BlueapiClient
from blueapi.client.event_bus import BlueskyStreamingError
from blueapi.config import ApplicationConfig
from blueapi.core import BlueskyContext
from blueapi.service.model import TaskRequest
from bluesky import plan_stubs as bps
from bluesky.utils import MsgGenerator

from mx_bluesky.common.parameters.components import MxBlueskyParameters
from mx_bluesky.common.parameters.constants import Status
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.hyperion.parameters.components import UDCCleanup, UDCDefaultState, Wait
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect
from mx_bluesky.hyperion.plan_runner import PlanError, PlanRunner


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
        self, current_visit: str | None, parameter_list: Sequence[MxBlueskyParameters]
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
            for parameters in parameter_list:
                LOGGER.info(
                    f"Executing plan with parameters: {parameters.model_dump_json(indent=2)}"
                )
                match parameters:
                    case LoadCentreCollect():
                        task_request = TaskRequest(
                            name="load_centre_collect",
                            params={"parameters": parameters},
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
                            params={"visit": current_visit},
                            instrument_session=instrument_session,
                        )
                        self._run_task_remotely(task_request)
                    case _:
                        raise AssertionError(
                            f"Unsupported instruction decoded from agamemnon {type(parameters)}"
                        )
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
            self.blueapi_client.get_state()
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
            self.blueapi_client.run_task(task_request)
        except BlueskyStreamingError as e:
            # We will receive a BlueskyStreamingError if the remote server
            # processed an abort during plan execution, but this is not
            # the only possible cause.
            if self.current_status == Status.ABORTING:
                LOGGER.info("Aborting local runner...")
                self.request_run_engine_abort()
            else:
                raise PlanError(f"Exception raised during plan execution: {e}") from e
