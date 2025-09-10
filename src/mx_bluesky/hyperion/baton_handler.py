from collections.abc import Sequence
from functools import partial
from typing import Any

from blueapi.core.context import BlueskyContext
from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp
from bluesky.utils import MsgGenerator, RunEngineInterrupted
from dodal.devices.baton import Baton

from mx_bluesky.common.experiment_plans.inner_plans.udc_default_state import (
    UDCDefaultDevices,
    move_to_udc_default_state,
)
from mx_bluesky.common.external_interaction.alerting import (
    AlertService,
    get_alerting_service,
)
from mx_bluesky.common.parameters.components import MxBlueskyParameters
from mx_bluesky.common.utils.context import (
    device_composite_from_context,
    find_device_in_context,
)
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.hyperion.experiment_plans.load_centre_collect_full_plan import (
    create_devices,
    load_centre_collect_full,
)
from mx_bluesky.hyperion.external_interaction.agamemnon import (
    create_parameters_from_agamemnon,
)
from mx_bluesky.hyperion.external_interaction.alerting.constants import Subjects
from mx_bluesky.hyperion.parameters.components import Wait
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect
from mx_bluesky.hyperion.plan_runner import PlanException, PlanRunner
from mx_bluesky.hyperion.utils.context import (
    clear_all_device_caches,
    setup_devices,
)

HYPERION_USER = "Hyperion"
NO_USER = "None"


def run_forever(runner: PlanRunner):
    try:
        while True:
            try:
                run_udc_when_requested(runner.context, runner)
            except PlanException as e:
                LOGGER.info(
                    "Caught exception during plan execution, stopped and waiting for baton.",
                    exc_info=e,
                )

    except RunEngineInterrupted:
        # In the event that BlueskyRunner.stop() or shutdown() was called then
        # RunEngine.abort() will have been called and we will get RunEngineInterrupted
        LOGGER.info(
            f"RunEngine was interrupted. Runner state is {runner.current_status}, "
            f"run engine is {runner.RE.state}"
        )


def run_udc_when_requested(context: BlueskyContext, runner: PlanRunner):
    """This will wait for the baton to be handed to hyperion and then run through the
    UDC queue from agamemnon until:
      1. There are no more instructions from agamemnon
      2. There is an error on the beamline
      3. The baton is requested by another party
      4. A shutdown is requested

    In the case of 1. 2. or 4. hyperion will immediately release the baton. In the case of
    3. the baton will be released after the next collection has finished."""

    baton = _get_baton(context)

    def acquire_baton() -> MsgGenerator:
        yield from _wait_for_hyperion_requested(baton)
        yield from bps.abs_set(baton.current_user, HYPERION_USER)

    def collect() -> MsgGenerator:
        """
        Move to the default state for collection, then enter a loop fetching instructions
        from Agamemnon and continue the loop until any of the following occur:
        * A user requests the baton away from Hyperion
        * Hyperion releases the baton when Agamemnon has no more instructions
        * The RunEngine raises a RequestAbort exception, most likely due to a shutdown command
        * A plan raises an exception not of type WarningException (which is then wrapped as a PlanException)
        Args:
            baton: The baton device
            runner: The runner
        """
        _raise_udc_start_alert(get_alerting_service())
        yield from _move_to_udc_default_state(context)

        # re-fetch the baton because the device has been reinstantiated
        baton = _get_baton(context)
        while (yield from _is_requesting_baton(baton)):
            yield from _fetch_and_process_agamemnon_instruction(baton, runner)

    def release_baton() -> MsgGenerator:
        # If hyperion has given up the baton itself we need to also release requested
        # user so that hyperion doesn't think we're requested again
        baton = _get_baton(context)
        previous_requested_user = yield from _safely_release_baton(baton)
        yield from bps.abs_set(baton.current_user, NO_USER, wait=True)
        _raise_baton_released_alert(get_alerting_service(), previous_requested_user)

    def collect_then_release() -> MsgGenerator:
        yield from bpp.contingency_wrapper(collect(), final_plan=release_baton)

    context.run_engine(acquire_baton())
    _initialise_udc(context)
    context.run_engine(collect_then_release())


def _initialise_udc(context: BlueskyContext):
    """
    Perform all initialisation that happens at the start of UDC just after the
    baton is acquired, but before we execute any plans or move hardware.

    Beamline devices are unloaded and reloaded in order to pick up any new configuration,
    bluesky context gets new set of devices.
    """
    LOGGER.info("Initialising mx-bluesky for UDC start...")
    clear_all_device_caches(context)
    setup_devices(context, False)


def _wait_for_hyperion_requested(baton: Baton):
    SLEEP_PER_CHECK = 0.1
    while True:
        requested_user = yield from bps.rd(baton.requested_user)
        if requested_user == HYPERION_USER:
            break
        yield from bps.sleep(SLEEP_PER_CHECK)


def _fetch_and_process_agamemnon_instruction(
    baton: Baton, runner: PlanRunner
) -> MsgGenerator:
    parameter_list: Sequence[MxBlueskyParameters] = create_parameters_from_agamemnon()
    if parameter_list:
        for parameters in parameter_list:
            LOGGER.info(
                f"Executing plan with parameters: {parameters.model_dump_json(indent=2)}"
            )
            match parameters:
                case LoadCentreCollect():
                    devices: Any = create_devices(runner.context)
                    yield from runner.execute_plan(
                        partial(load_centre_collect_full, devices, parameters)
                    )
                case Wait():
                    yield from runner.execute_plan(partial(_runner_sleep, parameters))
                case _:
                    raise AssertionError(
                        f"Unsupported instruction decoded from agamemnon {type(parameters)}"
                    )
    else:
        _raise_udc_completed_alert(get_alerting_service())
        # Release the baton for orderly exit from the instruction loop
        yield from _safely_release_baton(baton)


def _raise_udc_start_alert(alert_service: AlertService):
    alert_service.raise_alert(
        Subjects.UDC_STARTED, "Unattended Data Collection has started.", {}
    )


def _raise_baton_released_alert(alert_service: AlertService, baton_requester: str):
    alert_service.raise_alert(
        Subjects.UDC_BATON_RELEASED,
        f"Hyperion has released the baton. The baton is currently requested by:"
        f" {baton_requester}",
        {},
    )


def _raise_udc_completed_alert(alert_service: AlertService):
    alert_service.raise_alert(
        Subjects.UDC_COMPLETED,
        "Hyperion UDC has completed all pending Agamemnon requests.",
        {},
    )


def _runner_sleep(parameters: Wait) -> MsgGenerator:
    yield from bps.sleep(parameters.duration_s)


def _is_requesting_baton(baton: Baton) -> MsgGenerator:
    requested_user = yield from bps.rd(baton.requested_user)
    return requested_user == HYPERION_USER


def _move_to_udc_default_state(context: BlueskyContext):
    udc_default_devices = device_composite_from_context(context, UDCDefaultDevices)
    yield from move_to_udc_default_state(udc_default_devices)


def _get_baton(context: BlueskyContext) -> Baton:
    return find_device_in_context(context, "baton", Baton)


def _safely_release_baton(baton: Baton) -> MsgGenerator[str]:
    """Relinquish the requested user of the baton if it is not already requested
    by another user.

    Returns:
        The previously requested user, or NO_USER if no user was already requested.
    """
    requested_user = yield from bps.rd(baton.requested_user)
    if requested_user == HYPERION_USER:
        yield from bps.abs_set(baton.requested_user, NO_USER)
        return NO_USER
    return requested_user
