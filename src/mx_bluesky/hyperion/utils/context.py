from blueapi.core import BlueskyContext
from dodal.utils import get_beamline_based_on_environment_variable

import mx_bluesky.hyperion.experiment_plans as hyperion_plans
from mx_bluesky.common.utils.log import LOGGER


def setup_context() -> BlueskyContext:
    context = BlueskyContext()
    context.with_plan_module(hyperion_plans)

    context.with_dodal_module(get_beamline_based_on_environment_variable())

    LOGGER.info(f"Plans found in context: {context.plan_functions.keys()}")

    return context
