from collections.abc import Callable, Sequence
from functools import partial
from typing import Any

from blueapi.core import BlueskyContext
from bluesky import plan_stubs as bps
from bluesky.utils import MsgGenerator, RequestAbort
from dodal.devices.aperturescatterguard import ApertureScatterguard
from dodal.devices.detector.detector_motion import DetectorMotion
from dodal.devices.motors import XYZStage
from dodal.devices.robot import BartRobot
from dodal.devices.smargon import Smargon

from mx_bluesky.common.parameters.components import MxBlueskyParameters
from mx_bluesky.common.parameters.constants import Status
from mx_bluesky.common.utils.context import (
    device_composite_from_context,
    find_device_in_context,
)
from mx_bluesky.common.utils.exceptions import WarningError
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.hyperion.blueapi_plans import clean_up_udc, move_to_udc_default_state
from mx_bluesky.hyperion.experiment_plans import load_centre_collect_full
from mx_bluesky.hyperion.experiment_plans.load_centre_collect_full_plan import (
    create_devices,
)
from mx_bluesky.hyperion.experiment_plans.udc_default_state import UDCDefaultDevices
from mx_bluesky.hyperion.parameters.components import UDCCleanup, UDCDefaultState, Wait
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect
from mx_bluesky.hyperion.plan_runner import PlanError, PlanRunner


class InProcessRunner(PlanRunner):
    """Runner that executes experiments from inside a running Bluesky plan"""

    def __init__(self, context: BlueskyContext, dev_mode: bool) -> None:
        super().__init__(context, dev_mode)
        self._current_status: Status = Status.IDLE

    def decode_and_execute(
        self, current_visit: str | None, parameter_list: Sequence[MxBlueskyParameters]
    ) -> MsgGenerator:
        for parameters in parameter_list:
            LOGGER.info(
                f"Executing plan with parameters: {parameters.model_dump_json(indent=2)}"
            )
            match parameters:
                case LoadCentreCollect():
                    current_visit = parameters.visit
                    devices: Any = create_devices(self.context)
                    yield from self.execute_plan(
                        partial(load_centre_collect_full, devices, parameters)
                    )
                case Wait():
                    yield from self.execute_plan(partial(_runner_sleep, parameters))
                case UDCDefaultState():
                    udc_default_devices: UDCDefaultDevices = (
                        device_composite_from_context(self.context, UDCDefaultDevices)
                    )
                    yield from move_to_udc_default_state(udc_default_devices)
                case UDCCleanup():
                    yield from _clean_up_udc(self.context, current_visit)
                case _:
                    raise AssertionError(
                        f"Unsupported instruction decoded from agamemnon {type(parameters)}"
                    )
        return current_visit

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

        self._current_status = Status.BUSY

        try:
            yield from self.check_external_callbacks_are_alive()
            yield from experiment()
            self._current_status = Status.IDLE
        except WarningError as e:
            LOGGER.warning("Plan failed with warning", exc_info=e)
            self._current_status = Status.FAILED
        except RequestAbort:
            # This will occur when the run engine processes an abort when we shut down
            LOGGER.info("UDC Runner aborting")
            raise
        except Exception as e:
            LOGGER.error("Plan failed with exception", exc_info=e)
            self._current_status = Status.FAILED
            raise PlanError("Exception thrown in plan execution") from e

    def shutdown(self):
        """Performs a prompt shutdown. Aborts the run engine and terminates the loop
        waiting for messages."""

        LOGGER.info("Shutting down: Stopping the run engine gracefully")
        if self.current_status != Status.ABORTING:
            self._current_status = Status.ABORTING
            self.request_run_engine_abort()
            return

    @property
    def current_status(self) -> Status:
        return self._current_status


def _runner_sleep(parameters: Wait) -> MsgGenerator:
    yield from bps.sleep(parameters.duration_s)


def _clean_up_udc(context: BlueskyContext, visit: str) -> MsgGenerator:
    robot = find_device_in_context(context, "robot", BartRobot)
    smargon = find_device_in_context(context, "smargon", Smargon)
    aperture_scatterguard = find_device_in_context(
        context, "aperture_scatterguard", ApertureScatterguard
    )
    lower_gonio = find_device_in_context(context, "lower_gonio", XYZStage)
    detector_motion = find_device_in_context(context, "detector_motion", DetectorMotion)
    yield from clean_up_udc(
        visit,
        robot=robot,
        smargon=smargon,
        aperture_scatterguard=aperture_scatterguard,
        lower_gonio=lower_gonio,
        detector_motion=detector_motion,
    )
