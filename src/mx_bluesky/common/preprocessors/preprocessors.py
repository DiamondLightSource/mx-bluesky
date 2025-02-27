from bluesky.preprocessors import contingency_wrapper, plan_mutator
from bluesky.utils import make_decorator

from mx_bluesky.common.device_setup_plans.xbpm_feedback import (
    _check_and_pause_feedback_and_verify_undulator_gap,
    _unpause_xbpm_feedback_and_set_transmission_to_1,
)
from mx_bluesky.common.parameters.constants import PlanNameConstants
from mx_bluesky.common.protocols.protocols import DevicesForXbpmAndTransmissionWrapper


def transmission_and_xbpm_feedback_for_collection_for_fgs_wrapper(
    plan,
    devices: DevicesForXbpmAndTransmissionWrapper,
    desired_transmission_fraction: float,
):
    """Wrapper that can attach at the entry point of a beamline-specific XRC FGS plan. The wrapped plan will listen for an 'open_run' Message with metadata `PlanNameConstants.GRIDSCAN_OUTER`, then insert a plan to check and pause XBPM feedback, and verify undulator gap. It will also listen for the 'close_run' Message with the same metadata to unpause XBPM feedback. The unpausing is also added to a 'finally' block to ensure it still happens on any Exceptions"""

    def head(msg):
        yield from _check_and_pause_feedback_and_verify_undulator_gap(
            devices.undulator,
            devices.xbpm_feedback,
            devices.attenuator,
            devices.dcm,
            desired_transmission_fraction,
        )

        # Allow 'open_run' message to pass through
        yield msg

    def tail():
        yield from _unpause_xbpm_feedback_and_set_transmission_to_1(
            devices.xbpm_feedback, devices.attenuator
        )

    def insert_plans(msg):
        if msg.run:
            if (
                msg.command == "open_run"
                and PlanNameConstants.GRIDSCAN_OUTER in msg.run
            ):
                return head(msg), None
            elif (
                msg.command == "close_run"
                and PlanNameConstants.GRIDSCAN_OUTER in msg.run
            ):
                return None, tail()
        return None, None

    # Ensure unpausing xbpm feedback occurs if there's an exception during the run
    return (
        yield from contingency_wrapper(
            plan_mutator(plan, insert_plans),
            except_plan=_unpause_xbpm_feedback_and_set_transmission_to_1(
                devices.xbpm_feedback, devices.attenuator
            ),
        )
    )


transmission_and_xbpm_feedback_for_collection_for_fgs_decorator = make_decorator(
    transmission_and_xbpm_feedback_for_collection_for_fgs_wrapper
)
