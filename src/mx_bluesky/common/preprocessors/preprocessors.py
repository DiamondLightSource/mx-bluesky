from collections.abc import Callable

import bluesky.plan_stubs as bps
from bluesky import preprocessors as bpp
from bluesky.preprocessors import plan_mutator
from bluesky.utils import Msg, MsgGenerator, make_decorator

from mx_bluesky.common.device_setup_plans.xbpm_feedback import (
    check_and_pause_feedback,
    unpause_xbpm_feedback_and_set_transmission_to_1,
)
from mx_bluesky.common.parameters.constants import PlanNameConstants
from mx_bluesky.common.protocols.protocols import (
    XBPMPauseDevices,
)


def _create_insert_plans_mutator(
    run_key_to_wrap: PlanNameConstants | None = None,
    on_open: Callable[[Msg], MsgGenerator] | None = None,
    on_close: Callable[[], MsgGenerator] | None = None,
) -> Callable[[Msg], tuple[MsgGenerator | None, MsgGenerator | None]]:
    """
    Inserts plans to be executed when the run with the given name opens/closes.

    Args:
        run_key_to_wrap: The run name to insert before/after. If None (default) then
            insert on the first open/close run regardless of its name.
        on_open: The plan to perform just before the run opens
        on_close: The plan to perform just after the run closes

    """
    _wrapped_run_name: None | str = None

    def insert_plans(msg: Msg):
        # Wrap the specified run, or, if none specified, wrap the first run encountered
        nonlocal _wrapped_run_name

        match msg.command:
            case "open_run":
                # If we specified a run key, did we encounter it
                # If we didn't specify, then insert the plans and track the name of the run
                if on_open is not None and (
                    not (run_key_to_wrap or _wrapped_run_name)
                    or run_key_to_wrap is msg.run
                ):
                    _wrapped_run_name = msg.run if msg.run else "unnamed_run"
                    return on_open(msg), None
            case "close_run":
                # Check if the run tracked from above was closed
                # An exception is raised in the RunEngine if two unnamed runs are opened
                # at the same time, so we are safe from unpausing on the wrong run
                if on_close is not None and (
                    (_wrapped_run_name == "unnamed_run" and not msg.run)
                    or (msg.run and _wrapped_run_name and _wrapped_run_name is msg.run)
                ):
                    return None, on_close()

        return None, None

    return insert_plans


def pause_xbpm_feedback_during_collection_at_desired_transmission_wrapper(
    plan: MsgGenerator,
    devices: XBPMPauseDevices,
    desired_transmission_fraction: float,
    run_key_to_wrap: PlanNameConstants | None = None,
):
    """
    Sets the transmission for the data collection, ensuring the xbpm feedback is valid, then pauses
     XBPM feedback. Resets transmission and unpauses XBPM immediately after the run has finished.

    This wrapper should be attached to the entry point of any beamline-specific plan that may disrupt the XBPM feedback,
    such as a data collection or an x-ray center grid scan.
    This wrapper will do nothing if no runs are seen.

    XBPM feedback isn't reliable during collections due to:
     * Objects (e.g. attenuator) crossing the beam can cause large (incorrect) feedback movements
     * Lower transmissions/higher energies are less reliable for the xbpm

    So we need to keep the transmission at 100% and the feedback on when not collecting
    and then turn it off and set the correct transmission for collection. The feedback
    mostly accounts for slow thermal drift so it is safe to assume that the beam is
    stable during a collection.

    Args:
        plan: The plan performing the data collection.
        devices (XBPMPauseDevices): Composite device including The XBPM device that is responsible for keeping
            the beam in position, and attenuator
        desired_transmission_fraction (float): The desired transmission for the collection
        run_key_to_wrap: (str | None): Pausing XBPM and setting transmission is inserted before the 'open_run' message is seen with
            the matching run key, and unpausing and resetting transmission is inserted after the corresponding 'close_run' message is
            seen. If not specified, instead wrap the first run encountered.
    """

    def head(msg: Msg):
        yield from check_and_pause_feedback(
            devices.xbpm_feedback,
            devices.attenuator,
            desired_transmission_fraction,
        )

        # Allow 'open_run' message to pass through
        yield msg

    def tail():
        yield from unpause_xbpm_feedback_and_set_transmission_to_1(
            devices.xbpm_feedback, devices.attenuator
        )

    mutator = _create_insert_plans_mutator(run_key_to_wrap, head, tail)

    # Contingency wrapper can cause unpausing to occur on exception and again on close_run.
    # Not needed after https://github.com/bluesky/bluesky/issues/1891
    return (
        yield from bpp.contingency_wrapper(
            plan_mutator(plan, mutator),
            except_plan=lambda _: unpause_xbpm_feedback_and_set_transmission_to_1(
                devices.xbpm_feedback,
                devices.attenuator,
            ),
        )
    )


def set_transmission_and_trigger_xbpm_feedback_before_collection_wrapper(
    plan: MsgGenerator,
    devices: XBPMPauseDevices,
    desired_transmission_fraction: float,
    run_key_to_wrap: PlanNameConstants | None = None,
):
    """
    Sets the transmission and triggers xbpm feedback immediately before
    doing the specified run. Doesn't revert transmission at the end of the plan.

    Args:
        plan: The plan performing the data collection.
        devices (XBPMPauseDevices): Composite device including The XBPM device that is responsible for keeping
            the beam in position, and the attenuator
        desired_transmission_fraction (float): The desired transmission for the collection
        run_key_to_wrap: (str | None): 'Set transmission' and 'trigger XBPM device' is inserted before the 'open_run' message with
            the matching run key is seen. If not specified, instead wrap the first run encountered.
    """

    def head(msg: Msg):
        yield from bps.mv(devices.attenuator, desired_transmission_fraction)
        yield from bps.trigger(devices.xbpm_feedback)

        # Allow 'open_run' message to pass through
        yield msg

    mutator = _create_insert_plans_mutator(run_key_to_wrap, head)

    return (yield from plan_mutator(plan, mutator))


set_transmission_and_trigger_xbpm_feedback_before_collection_decorator = make_decorator(
    set_transmission_and_trigger_xbpm_feedback_before_collection_wrapper
)


pause_xbpm_feedback_during_collection_at_desired_transmission_decorator = (
    make_decorator(
        pause_xbpm_feedback_during_collection_at_desired_transmission_wrapper
    )
)
