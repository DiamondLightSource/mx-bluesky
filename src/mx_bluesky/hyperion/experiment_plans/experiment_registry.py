from __future__ import annotations

from collections.abc import Callable
from typing import TypedDict

import mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan as flyscan_xray_centre_plan
import mx_bluesky.hyperion.experiment_plans.rotation_scan_plan as rotation_scan_plan
from mx_bluesky.common.parameters.gridscan import (
    GridScanWithEdgeDetect,
    PinTipCentreThenXrayCentre,
    RobotLoadThenCentre,
)
from mx_bluesky.hyperion.experiment_plans import (
    grid_detect_then_xray_centre_plan,
    load_centre_collect_full_plan,
    pin_centre_then_xray_centre_plan,
    robot_load_then_centre_plan,
)
from mx_bluesky.hyperion.external_interaction.callbacks.common.callback_util import (
    CallbacksFactory,
    create_gridscan_callbacks,
    create_load_centre_collect_callbacks,
    create_robot_load_and_centre_callbacks,
    create_rotation_callbacks,
)
from mx_bluesky.hyperion.parameters.gridscan import HyperionThreeDGridScan
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect
from mx_bluesky.hyperion.parameters.rotation import MultiRotationScan, RotationScan


def not_implemented():
    raise NotImplementedError


def do_nothing():
    pass


class ExperimentRegistryEntry(TypedDict):
    setup: Callable
    param_type: type[
        HyperionThreeDGridScan
        | GridScanWithEdgeDetect
        | RotationScan
        | MultiRotationScan
        | PinTipCentreThenXrayCentre
        | RobotLoadThenCentre
        | LoadCentreCollect
    ]
    callbacks_factory: CallbacksFactory


PLAN_REGISTRY: dict[str, ExperimentRegistryEntry] = {
    "flyscan_xray_centre": {
        "setup": flyscan_xray_centre_plan.create_devices,
        "param_type": HyperionThreeDGridScan,
        "callbacks_factory": create_gridscan_callbacks,
    },
    "grid_detect_then_xray_centre": {
        "setup": grid_detect_then_xray_centre_plan.create_devices,
        "param_type": GridScanWithEdgeDetect,
        "callbacks_factory": create_gridscan_callbacks,
    },
    "rotation_scan": {
        "setup": rotation_scan_plan.create_devices,
        "param_type": RotationScan,
        "callbacks_factory": create_rotation_callbacks,
    },
    "pin_tip_centre_then_xray_centre": {
        "setup": pin_centre_then_xray_centre_plan.create_devices,
        "param_type": PinTipCentreThenXrayCentre,
        "callbacks_factory": create_gridscan_callbacks,
    },
    "robot_load_then_centre": {
        "setup": robot_load_then_centre_plan.create_devices,
        "param_type": RobotLoadThenCentre,
        "callbacks_factory": create_robot_load_and_centre_callbacks,
    },
    "multi_rotation_scan": {
        "setup": rotation_scan_plan.create_devices,
        "param_type": MultiRotationScan,
        "callbacks_factory": create_rotation_callbacks,
    },
    "load_centre_collect_full": {
        "setup": load_centre_collect_full_plan.create_devices,
        "param_type": LoadCentreCollect,
        "callbacks_factory": create_load_centre_collect_callbacks,
    },
}


class PlanNotFound(Exception):
    pass
