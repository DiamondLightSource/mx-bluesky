from inspect import getfullargspec

import pytest

import mx_bluesky.hyperion.experiment_plans as plan_module
from mx_bluesky.common.parameters.components import MxBlueskyParameters
from mx_bluesky.hyperion.experiment_plans import __all__ as exposed_plans
from mx_bluesky.hyperion.experiment_plans.experiment_registry import (
    PLAN_REGISTRY,
    do_nothing,
)


def test_experiment_registry_param_types():
    for plan in PLAN_REGISTRY.keys():
        assert issubclass(PLAN_REGISTRY[plan]["param_type"], MxBlueskyParameters)


def test_exposed_plans_in_reg():
    for plan in exposed_plans:
        assert plan in PLAN_REGISTRY.keys()


@pytest.mark.skip(
    reason="Conflicting MsgGenerator import strangeness https://github.com/DiamondLightSource/mx-bluesky/pull/564"
)
def test_param_types_in_registry_match_plan():
    for plan in exposed_plans:
        plan_function = getattr(plan_module, plan)
        plan_args = getfullargspec(plan_function)
        param_arg_type = plan_args.annotations["parameters"]
        assert PLAN_REGISTRY[plan]["param_type"].__name__ in param_arg_type


def test_do_nothing():
    do_nothing()
