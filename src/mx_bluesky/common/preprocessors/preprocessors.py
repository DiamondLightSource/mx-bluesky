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


def transmission_and_xbpm_feedback_for_collection_wrapper(
    plan: MsgGenerator,
    devices: XBPMPauseDevices,
    desired_transmission_fraction: float,
    run_key_to_wrap: PlanNameConstants | None = None,
):
    """
    Sets the transmission for the data collection, ensuring the xbpm feedback is valid, then resets it immediately after
    the run has finished.

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
        run_key_to_wrap: (str | None): Pausing XBPM and setting transmission is inserted after the 'open_run' message is seen with
        the matching run key, and unpausing and resetting transmission is inserted after the corresponding 'close_run' message is
        seen. If not specified, instead wrap the first run encountered.
    """

    _wrapped_run_name: None | str = None

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
            case "close_run":
                # Check if the run tracked from above was closed
                # An exception is raised in the RunEngine if two unnamed runs are opened
                # at the same time, so we are safe from unpausing on the wrong run
                if (_wrapped_run_name == "unnamed_run" and not msg.run) or (
                    msg.run and _wrapped_run_name and _wrapped_run_name is msg.run
                ):
                    return None, tail()

        return None, None

    # Contingency wrapper can cause unpausing to occur on exception and again on close_run.
    # Not needed after https://github.com/bluesky/bluesky/issues/1891
    return (
        yield from bpp.contingency_wrapper(
            plan_mutator(plan, insert_plans),
            except_plan=lambda _: unpause_xbpm_feedback_and_set_transmission_to_1(
                devices.xbpm_feedback,
                devices.attenuator,
            ),
        )
    )


transmission_and_xbpm_feedback_for_collection_decorator = make_decorator(
    transmission_and_xbpm_feedback_for_collection_wrapper
)
