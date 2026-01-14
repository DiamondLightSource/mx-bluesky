import bluesky.plan_stubs as bps
from bluesky.preprocessors import plan_mutator
from bluesky.utils import Msg, MsgGenerator, make_decorator

from mx_bluesky.common.parameters.constants import PlanNameConstants
from mx_bluesky.common.protocols.protocols import (
    XBPMPauseDevices,
)


def i04_transmission_and_xbpm_feedback_for_collection_wrapper(
    plan: MsgGenerator,
    devices: XBPMPauseDevices,
    desired_transmission_fraction: float,
    run_key_to_wrap: PlanNameConstants | None = None,
):
    """
    Sets the transmission for the data collection, ensuring the xbpm feedback is valid. Triggers xbpm feedback immediately before
    doing the grid scan. Doesn't revert transmission at the end of the plan.

    Args:
        plan: The plan performing the data collection.
        devices (XBPMPauseDevices): Composite device including The XBPM device that is responsible for keeping
                                                        the beam in position, and attenuator
        desired_transmission_fraction (float): The desired transmission for the collection
        run_key_to_wrap: (str | None): Pausing XBPM and setting transmission is inserted after the 'open_run' message is seen with
        the matching run key, and unpausing and resetting transmission is inserted after the corresponding 'close_run' message is
        seen. If not specified, instead wrap the first run encountered.
    """

    _wrapped_run_name: None | str = None

    def head(msg: Msg):
        yield from bps.mv(devices.attenuator, desired_transmission_fraction)
        yield from bps.trigger(devices.xbpm_feedback)

        # Allow 'open_run' message to pass through
        yield msg

    def insert_plans(msg: Msg):
        # Wrap the specified run, or, if none specified, wrap the first run encountered
        nonlocal _wrapped_run_name

        match msg.command:
            case "open_run":
                # If we specified a run key, did we encounter it
                # If we didn't specify, then insert the plans and track the name of the run
                if (
                    not (run_key_to_wrap or _wrapped_run_name)
                    or run_key_to_wrap is msg.run
                ):
                    _wrapped_run_name = msg.run if msg.run else "unnamed_run"
                    return head(msg), None

        return None, None

    # Contingency wrapper can cause unpausing to occur on exception and again on close_run.
    # Not needed after https://github.com/bluesky/bluesky/issues/1891
    return (yield from plan_mutator(plan, insert_plans))


i04_transmission_and_xbpm_feedback_for_collection_decorator = make_decorator(
    i04_transmission_and_xbpm_feedback_for_collection_wrapper
)
