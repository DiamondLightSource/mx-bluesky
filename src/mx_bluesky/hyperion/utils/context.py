from blueapi.core import BlueskyContext
from dodal.common.beamlines.beamline_utils import clear_devices
from dodal.utils import collect_factories, get_beamline_based_on_environment_variable

import mx_bluesky.hyperion.experiment_plans as hyperion_plans
from mx_bluesky.common.utils.log import LOGGER


def setup_context(dev_mode: bool = False) -> BlueskyContext:
    context = BlueskyContext()
    context.with_plan_module(hyperion_plans)

    setup_devices(context, dev_mode)

    LOGGER.info(f"Plans found in context: {context.plan_functions.keys()}")

    return context


def clear_all_device_caches(context: BlueskyContext):
    context.unregister_all_devices()
    clear_devices()

    for f in collect_factories(get_beamline_based_on_environment_variable()).values():
        if hasattr(f, "cache_clear"):
            f.cache_clear()  # type: ignore


def setup_devices(context: BlueskyContext, dev_mode: bool):
    context.with_dodal_module(
        get_beamline_based_on_environment_variable(),
        mock=dev_mode,
    )
