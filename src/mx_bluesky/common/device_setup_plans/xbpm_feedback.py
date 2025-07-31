from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp
from bluesky.utils import MsgGenerator
from dodal.common.beamlines.commissioning_mode import is_commissioning_mode_enabled
from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
from dodal.devices.xbpm_feedback import Pause, XBPMFeedback

from mx_bluesky.common.utils.log import LOGGER

IGNORE_FEEDBACK_THRESHOLD_PC = 100000


def unpause_xbpm_feedback_and_set_transmission_to_1(
    xbpm_feedback: XBPMFeedback, attenuator: BinaryFilterAttenuator
):
    """Turns the XBPM feedback back on and sets transmission to 1 so that it keeps the
    beam aligned whilst not collecting.

    Args:
        xbpm_feedback (XBPMFeedback): The XBPM device that is responsible for keeping
                                      the beam in position
        attenuator (BinaryFilterAttenuator): The attenuator used to set transmission
    """
    yield from bps.mv(xbpm_feedback.pause_feedback, Pause.RUN, attenuator, 1.0)  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809


def check_and_pause_feedback(
    xbpm_feedback: XBPMFeedback,
    attenuator: BinaryFilterAttenuator,
    desired_transmission_fraction: float,
):
    """Checks that the xbpm is in position before then turning it off and setting a new
    transmission.

    Args:
        xbpm_feedback (XBPMFeedback): The XBPM device that is responsible for keeping
                                      the beam in position
        attenuator (BinaryFilterAttenuator): The attenuator used to set transmission
        desired_transmission_fraction (float): The desired transmission to set after
                                               turning XBPM feedback off.

    """
    yield from bps.mv(attenuator, 1.0)  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
    LOGGER.info("Waiting for XBPM feedback to be stable")
    yield from bps.trigger(xbpm_feedback, wait=True)
    LOGGER.info(
        f"XPBM feedback in position, pausing and setting transmission to {desired_transmission_fraction}"
    )
    yield from bps.mv(xbpm_feedback.pause_feedback, Pause.PAUSE)  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
    yield from bps.mv(attenuator, desired_transmission_fraction)  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809


def feedback_wrapper_for_commissioning_mode(
    xbpm_feedback: XBPMFeedback, plan: MsgGenerator
) -> MsgGenerator:
    """If commissioning mode is enabled, increase the feedback threshold such that
     feedback is effectively ignored, then restore it after the plan is complete.
    Args:
        xbpm_feedback: The feedback device
        plan: The plan to wrap
    """
    if not is_commissioning_mode_enabled():
        yield from plan
    else:
        old_threshold_pc = yield from bps.rd(xbpm_feedback.threshold_pc)
        LOGGER.info(f"Saving previous XBPM threshold of {old_threshold_pc}%")

        yield from bps.abs_set(xbpm_feedback.threshold_pc, IGNORE_FEEDBACK_THRESHOLD_PC)

        def restore_feedback_threshold() -> MsgGenerator:
            LOGGER.info(f"Restoring previous XBPM threshold of {old_threshold_pc}")
            yield from bps.abs_set(xbpm_feedback.threshold_pc, old_threshold_pc)

        yield from bpp.finalize_wrapper(plan, restore_feedback_threshold)
