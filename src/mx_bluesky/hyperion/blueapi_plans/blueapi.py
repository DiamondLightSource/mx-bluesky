"""
This module is the bluesky plan module for use with hyperion-blueapi.
Importing this module will configure debug and info logging as a side-effect - so this module should not be
imported directly by other components as it is intended only as the entry-point for BlueAPI.
"""

from mx_bluesky.common.utils.log import setup_hyperion_blueapi_logging
from mx_bluesky.hyperion.blueapi_plans.in_process import (
    LoadCentreCollect,
    LoadCentreCollectComposite,
    UDCDefaultDevices,
    clean_up_udc,
    load_centre_collect,
    move_to_udc_default_state,
    robot_unload,
)
from mx_bluesky.hyperion.parameters.constants import CONST

__all__ = [
    "LoadCentreCollectComposite",
    "LoadCentreCollect",
    "UDCDefaultDevices",
    "clean_up_udc",
    "load_centre_collect",
    "move_to_udc_default_state",
    "robot_unload",
]


def _init_plan_module():
    """Initialisation hooks for hyperion-blueapi"""
    setup_hyperion_blueapi_logging(CONST.LOG_FILE_NAME)


_init_plan_module()
