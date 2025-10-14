"""
This module contains the bluesky plan entry points for use with hyperion-blueapi.
"""

from bluesky.utils import MsgGenerator
from dodal.common import inject
from dodal.devices.aperturescatterguard import ApertureScatterguard
from dodal.devices.motors import XYZStage
from dodal.devices.robot import BartRobot
from dodal.devices.smargon import Smargon

from mx_bluesky.common.device_setup_plans.robot_load_unload import (
    robot_unload as _robot_unload,
)
from mx_bluesky.common.experiment_plans.inner_plans.udc_default_state import (
    UDCDefaultDevices,
)
from mx_bluesky.common.experiment_plans.inner_plans.udc_default_state import (
    move_to_udc_default_state as _move_to_udc_default_state,
)
from mx_bluesky.hyperion.experiment_plans.load_centre_collect_full_plan import (
    LoadCentreCollectComposite,
)
from mx_bluesky.hyperion.experiment_plans.load_centre_collect_full_plan import (
    load_centre_collect_full as _load_centre_collect_full,
)
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect

__all__ = [
    "LoadCentreCollectComposite",
    "LoadCentreCollect",
    "UDCDefaultDevices",
    "load_centre_collect",
    "move_to_udc_default_state",
    "robot_unload",
]


def load_centre_collect(
    parameters: LoadCentreCollect, composite: LoadCentreCollectComposite = inject()
) -> MsgGenerator:
    yield from _load_centre_collect_full(composite, parameters)


def robot_unload(
    visit: str,
    robot: BartRobot = inject("robot"),
    smargon: Smargon = inject("smargon"),
    aperture_scatterguard: ApertureScatterguard = inject("aperture_scatterguard"),
    lower_gonio: XYZStage = inject("lower_gonio"),
) -> MsgGenerator:
    yield from _robot_unload(robot, smargon, aperture_scatterguard, lower_gonio, visit)


def move_to_udc_default_state(
    composite: UDCDefaultDevices = inject(),
) -> MsgGenerator:
    yield from _move_to_udc_default_state(composite)
