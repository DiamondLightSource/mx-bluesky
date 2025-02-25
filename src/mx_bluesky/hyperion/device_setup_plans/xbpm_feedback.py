from bluesky import plan_stubs as bps
from bluesky.preprocessors import finalize_wrapper
from bluesky.utils import make_decorator
from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
from dodal.devices.dcm import DCM
from dodal.devices.undulator import Undulator
from dodal.devices.xbpm_feedback import Pause, XBPMFeedback

from mx_bluesky.common.utils.log import LOGGER


def _check_and_pause_feedback(
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


def _unpause_xbpm_feedback_and_set_transmission_to_1(
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


def transmission_and_xbpm_feedback_for_collection_wrapper(
    plan,
    undulator: Undulator,
    xbpm_feedback: XBPMFeedback,
    attenuator: BinaryFilterAttenuator,
    dcm: DCM,
    desired_transmission_fraction: float,
):
    """Sets the transmission for the data collection, ensuring the xbpm feedback is valid
    this wrapper should be run around every data collection or movement that may disrupt
    the XBPM feedback.

    XBPM feedback isn't reliable during collections due to:
     * Objects (e.g. attenuator) crossing the beam can cause large (incorrect) feedback movements
     * Lower transmissions/higher energies are less reliable for the xbpm

    So we need to keep the transmission at 100% and the feedback on when not collecting
    and then turn it off and set the correct transmission for collection. The feedback
    mostly accounts for slow thermal drift so it is safe to assume that the beam is
    stable during a collection.

    In the case of a beam dump, undulator gap may not return. Therefore, we check here
    that the undulator gap is correct after XBPM is stable, and before collection.

    Args:
        plan: The plan performing the data collection
        xbpm_feedback (XBPMFeedback): The XBPM device that is responsible for keeping
                                      the beam in position
        attenuator (BinaryFilterAttenuator): The attenuator used to set transmission
        desired_transmission_fraction (float): The desired transmission for the collection
    """

    def _inner_plan():
        yield from _check_and_pause_feedback_and_verify_undulator_gap(
            undulator,
            xbpm_feedback,
            attenuator,
            dcm,
            desired_transmission_fraction,
        )
        return (yield from plan)

    return (
        yield from finalize_wrapper(
            _inner_plan(),
            _unpause_xbpm_feedback_and_set_transmission_to_1(xbpm_feedback, attenuator),
        )
    )


def _check_and_pause_feedback_and_verify_undulator_gap(
    undulator: Undulator,
    xbpm_feedback: XBPMFeedback,
    attenuator: BinaryFilterAttenuator,
    dcm: DCM,
    desired_transmission_fraction: float,
):
    yield from _check_and_pause_feedback(
        xbpm_feedback, attenuator, desired_transmission_fraction
    )
    # Verify Undulator gap is correct, as may not be after a beam dump
    energy_in_kev = yield from bps.rd(dcm.energy_in_kev.user_readback)
    yield from bps.abs_set(undulator, energy_in_kev, wait=True)


transmission_and_xbpm_feedback_for_collection_decorator = make_decorator(
    transmission_and_xbpm_feedback_for_collection_wrapper
)
