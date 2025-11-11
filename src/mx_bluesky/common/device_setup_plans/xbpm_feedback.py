from bluesky import plan_stubs as bps
from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
from dodal.devices.xbpm_feedback import Pause, XBPMFeedback

from mx_bluesky.common.utils.log import LOGGER


def unpause_xbpm_feedback_and_set_transmission_to_1(
    xbpm_feedback: XBPMFeedback,
    attenuator: BinaryFilterAttenuator,
    timeout_for_stable: float = 0,
):
    """Turns the XBPM feedback back on and sets transmission to 1 so that it keeps the
    beam aligned whilst not collecting.

    Args:
        xbpm_feedback (XBPMFeedback): The XBPM device that is responsible for keeping
                                      the beam in position
        attenuator (BinaryFilterAttenuator): The attenuator used to set transmission
        timeout_for_stable: If specified and non-zero, specifies the time in seconds to wait for
            feedback to stabilise, otherwise we do not wait.
    """
    yield from bps.mv(xbpm_feedback.pause_feedback, Pause.RUN, attenuator, 1.0)
    if timeout_for_stable:
        yield from bps.trigger(xbpm_feedback, group="feedback")
        yield from bps.wait(group="feedback", timeout=timeout_for_stable)


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
    yield from bps.mv(attenuator, 1.0)
    LOGGER.info("Waiting for XBPM feedback to be stable")
    yield from bps.trigger(xbpm_feedback, wait=True)
    LOGGER.info(
        f"XPBM feedback in position, pausing and setting transmission to {desired_transmission_fraction}"
    )
    yield from bps.mv(xbpm_feedback.pause_feedback, Pause.PAUSE)
    yield from bps.mv(attenuator, desired_transmission_fraction)
