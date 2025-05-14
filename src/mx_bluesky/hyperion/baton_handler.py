from collections.abc import Sequence

from blueapi.core import BlueskyContext
from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp
from dodal.devices.baton import Baton

from mx_bluesky.common.parameters.components import MxBlueskyParameters
from mx_bluesky.common.utils.context import find_device_in_context
from mx_bluesky.common.external_interaction.alerting import set_alerting_service
from mx_bluesky.common.external_interaction.alerting.alert_manager import (
    AlertManagerAlertService,
)
from mx_bluesky.common.utils.exceptions import WarningException
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.hyperion.experiment_plans.load_centre_collect_full_plan import (
    LoadCentreCollectComposite,
    create_devices,
    load_centre_collect_full,
)
from mx_bluesky.hyperion.external_interaction.agamemnon import (
    create_parameters_from_agamemnon,
)
from mx_bluesky.hyperion.external_interaction.config_server import HyperionFeatureFlags
from mx_bluesky.hyperion.parameters.components import Wait
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect
from mx_bluesky.hyperion.utils.context import (
    clear_all_device_caches,
    setup_devices,
)

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
            parameter_list: Sequence[MxBlueskyParameters] = (
                create_parameters_from_agamemnon()
            )
            if parameter_list:
                for parameters in parameter_list:
                    match parameters:
                        case LoadCentreCollect():
                            yield from load_centre_collect_full(composite, parameters)
                        case Wait():
                            yield from bps.sleep(parameters.duration_s)
                        case _:
                            raise AssertionError(
                                f"Unsupported instruction decoded from agamemnon {type(parameters)}"
                            )
            else:
                yield from bps.mv(baton.requested_user, NO_USER)

        yield from bpp.contingency_wrapper(
            inner_loop(), except_plan=ignore_sample_errors, auto_raise=False
        )
        requested_user = yield from bps.rd(baton.requested_user)


def move_to_default_state():
    # To be filled in in https://github.com/DiamondLightSource/mx-bluesky/issues/396
    yield from bps.null()


def initialise_udc(context: BlueskyContext, dev_mode: bool = False):
    """
    Perform all initialisation that happens at the start of UDC just after the
    baton is acquired, but before we execute any plans or move hardware.

    Beamline devices are unloaded and reloaded in order to pick up any new configuration,
    bluesky context gets new set of devices.
    """
    LOGGER.info("Initialising mx-bluesky for UDC start...")
    clear_all_device_caches(context)
    setup_devices(context, dev_mode)


def _get_baton(context: BlueskyContext) -> Baton:
    return find_device_in_context(context, "baton", Baton)


def run_udc_when_requested(context: BlueskyContext, dev_mode: bool = False):
    """This will wait for the baton to be handed to hyperion and then run through the
    UDC queue from agamemnon until:
      1. There are no more instructions from agamemnon
      2. There is an error on the beamline
      3. The baton is requested by another party

    In the case of 1. or 2. hyperion will immediately release the baton. In the case of
    3. the baton will be released after the next collection has finished."""

    flags = HyperionFeatureFlags()
    flags.update_self_from_server()
    set_alerting_service(AlertManagerAlertService(flags.alert_manager_url))

    baton = _get_baton(context)
    yield from wait_for_hyperion_requested(baton)
    yield from bps.abs_set(baton.current_user, HYPERION_USER)

    def initialise_then_collect():
        initialise_udc(context, dev_mode)
        yield from move_to_default_state()

        # re-fetch the baton because the device has been reinstantiated
        new_baton = _get_baton(context)
        composite = create_devices(context)
        yield from main_hyperion_loop(new_baton, composite)

    def release_baton():
        # If hyperion has given up the baton itself we need to also release requested
        # user so that hyperion doesn't think we're requested again
        baton = _get_baton(context)
        requested_user = yield from bps.rd(baton.requested_user)
        if requested_user == HYPERION_USER:
            yield from bps.abs_set(baton.requested_user, NO_USER)
        yield from bps.abs_set(baton.current_user, NO_USER)

    yield from bpp.contingency_wrapper(
        initialise_then_collect(), final_plan=release_baton
    )
