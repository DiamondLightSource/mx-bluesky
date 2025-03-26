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
    yield from bps.null()


def baton_handler(baton: Baton, composite: LoadCentreCollectComposite):
    yield from wait_for_hyperion_requested(baton)
    yield from bps.abs_set(baton.current_user, HYPERION_USER)

    def default_state_then_collect():
        yield from move_to_default_state()
        yield from main_hyperion_loop(baton, composite)

    def release_baton():
        yield from bps.abs_set(baton.requested_user, NO_USER)
        yield from bps.abs_set(baton.current_user, NO_USER)

    yield from bpp.contingency_wrapper(
        default_state_then_collect(), final_plan=release_baton
    )
