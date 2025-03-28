from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp
from dodal.devices.baton import Baton

from mx_bluesky.common.utils.exceptions import WarningException
from mx_bluesky.hyperion.experiment_plans.load_centre_collect_full_plan import (
    LoadCentreCollectComposite,
    load_centre_collect_full,
)
from mx_bluesky.hyperion.external_interaction.agamemnon import (
    create_parameters_from_agamemnon,
)
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect

HYPERION_USER = "Hyperion"
NO_USER = "None"


def wait_for_hyperion_requested(baton: Baton):
    SLEEP_PER_CHECK = 0.1
    while True:
        requested_user = yield from bps.rd(baton.requested_user)
        if requested_user == HYPERION_USER:
            break
        yield from bps.sleep(SLEEP_PER_CHECK)


def ignore_sample_errors(exception: Exception):
    yield from bps.null()
    # For sample errors we want to continue the loop
    if not isinstance(exception, WarningException):
        raise exception


def main_hyperion_loop(baton: Baton, composite: LoadCentreCollectComposite):
    requested_user = yield from bps.rd(baton.requested_user)
    while requested_user == HYPERION_USER:

        def inner_loop():
            parameters: LoadCentreCollect | None = create_parameters_from_agamemnon()  # type: ignore # not complete until https://github.com/DiamondLightSource/mx-bluesky/issues/773
            if parameters:
                yield from load_centre_collect_full(composite, parameters)
            else:
                yield from bps.mv(baton.requested_user, NO_USER)

        yield from bpp.contingency_wrapper(
            inner_loop(), except_plan=ignore_sample_errors, auto_raise=False
        )
        requested_user = yield from bps.rd(baton.requested_user)


def move_to_default_state():
    # To be filled in in https://github.com/DiamondLightSource/mx-bluesky/issues/396
    yield from bps.null()


def run_udc_when_requested(baton: Baton, composite: LoadCentreCollectComposite):
    """This will wait for the baton to be handed to hyperion and then run through the
    UDC queue from agamemnon until:
      1. There are no more instructions from agamemnon
      2. There is an error on the beamline
      3. The baton is requested by another party

    In the case of 1. or 2. hyperion will immediately release the baton. In the case of
    3. the baton will be released after the next collection has finished."""

    yield from wait_for_hyperion_requested(baton)
    yield from bps.abs_set(baton.current_user, HYPERION_USER)

    def default_state_then_collect():
        yield from move_to_default_state()
        yield from main_hyperion_loop(baton, composite)

    def release_baton():
        # If hyperion has given up the baton itself we need to also release requested
        # user so that hyperion doesn't think we're requested again
        requested_user = yield from bps.rd(baton.requested_user)
        if requested_user == HYPERION_USER:
            yield from bps.abs_set(baton.requested_user, NO_USER)
        yield from bps.abs_set(baton.current_user, NO_USER)

    yield from bpp.contingency_wrapper(
        default_state_then_collect(), final_plan=release_baton
    )
