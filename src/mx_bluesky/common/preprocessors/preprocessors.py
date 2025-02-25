from bluesky.preprocessors import (
    finalize_wrapper,
    plan_mutator,
)
from bluesky.utils import make_decorator

from mx_bluesky.common.parameters.constants import PlanNameConstants
from mx_bluesky.common.protocols.protocols import DevicesForXbpmAndTransmissionWrapper
from mx_bluesky.hyperion.device_setup_plans.xbpm_feedback import (
    _check_and_pause_feedback_and_verify_undulator_gap,
    _unpause_xbpm_feedback_and_set_transmission_to_1,
)

# TODO: Move xbpm feedback to common


def transmission_and_xbpm_feedback_for_collection_for_fgs_wrapper(
    plan,
    devices: DevicesForXbpmAndTransmissionWrapper,
    desired_transmission_fraction: float,
):
    """Wrapper that can attach at the entry point of a beamline-specific XRC FGS plan. The wrapped plan will listen for an 'open_run' Message with metadata `PlanNameConstants.GRIDSCAN_OUTER`, then insert a plan to check and pause XBPM feedback, and verify undulator gap. It will also listen for the 'close_run' Message with the same metadata to unpause XBPM feedback. The unpausing is also added to a 'finally' block to ensure it still happens on any Exceptions"""

    def head():
        yield from _check_and_pause_feedback_and_verify_undulator_gap(
            devices.undulator,
            devices.xbpm_feedback,
            devices.attenuator,
            devices.dcm,
            desired_transmission_fraction,
        )

    def tail():
        yield from _unpause_xbpm_feedback_and_set_transmission_to_1(
            devices.xbpm_feedback, devices.attenuator
        )

    def insert_plans(msg):
        if msg.command == "open_run" and PlanNameConstants.GRIDSCAN_OUTER in msg.kwargs:
            return head(), None
        elif (
            msg.command == "close_run"
            and PlanNameConstants.GRIDSCAN_OUTER in msg.kwargs
        ):
            return None, tail()
        else:
            return None, None

    return (
        yield from finalize_wrapper(
            plan_mutator(plan, insert_plans),
            _unpause_xbpm_feedback_and_set_transmission_to_1(
                devices.xbpm_feedback, devices.attenuator
            ),
        )
    )


transmission_and_xbpm_feedback_for_collection_for_fgs_decorator = make_decorator(
    transmission_and_xbpm_feedback_for_collection_for_fgs_wrapper
)
