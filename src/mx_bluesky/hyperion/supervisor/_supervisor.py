from collections.abc import Sequence
from pathlib import Path

from blueapi.client.client import BlueapiClient
from blueapi.config import ApplicationConfig, ConfigLoader
from blueapi.core import BlueskyContext
from blueapi.service.model import TaskRequest
from bluesky import plan_stubs as bps
from bluesky.utils import MsgGenerator

from mx_bluesky.common.parameters.components import MxBlueskyParameters
from mx_bluesky.common.parameters.constants import Status
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.hyperion.parameters.components import UDCCleanup, UDCDefaultState, Wait
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect
from mx_bluesky.hyperion.plan_runner import PlanRunner


def create_context() -> BlueskyContext:
    config_path = Path("src/mx_bluesky/hyperion/supervisor/supervisor_config.yaml")
    loader = ConfigLoader(ApplicationConfig)
    loader.use_values_from_yaml(config_path)
    app_config = loader.load()
    context = BlueskyContext(configuration=app_config)
    return context


class SupervisorRunner(PlanRunner):
    """Runner that executes plans by delegating to a remote blueapi instance"""

    def __init__(
        self,
        bluesky_context: BlueskyContext,
        client_config: ApplicationConfig,
        dev_mode: bool,
    ):
        super().__init__(bluesky_context, dev_mode)
        self._blueapi_client = BlueapiClient.from_config(client_config)

    def decode_and_execute(
        self, current_visit: str | None, parameter_list: Sequence[MxBlueskyParameters]
    ) -> MsgGenerator:
        # TODO determine what is the instrument session for udc_default_state etc.
        instrument_session = current_visit or "NO_VISIT"
        for parameters in parameter_list:
            LOGGER.info(
                f"Executing plan with parameters: {parameters.model_dump_json(indent=2)}"
            )
            match parameters:
                case LoadCentreCollect():  # TODO
                    pass
                case Wait():
                    yield from bps.sleep(parameters.duration_s)
                case UDCDefaultState():
                    task_request = TaskRequest(
                        name="move_to_udc_default_state",
                        params={},
                        instrument_session=instrument_session,
                    )
                    self._blueapi_client.run_task(task_request)
                case UDCCleanup():
                    task_request = TaskRequest(
                        name="clean_up_udc",
                        params={"visit": current_visit},
                        instrument_session=instrument_session,
                    )
                    self._blueapi_client.run_task(task_request)
                case _:
                    raise AssertionError(
                        f"Unsupported instruction decoded from agamemnon {type(parameters)}"
                    )
        return current_visit

    def reset_callback_watchdog_timer(self):
        pass

    @property
    def current_status(self) -> Status:
        return Status.FAILED  # TODO

    def shutdown(self):
        pass
