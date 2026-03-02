"""
This module is the bluesky plan module for use with hyperion-blueapi.
Importing this module will configure debug and info logging as a side-effect - so this module should not be
imported directly by other components as it is intended only as the entry-point for BlueAPI.
"""
from bluesky.preprocessors import set_run_key_decorator, run_decorator
from bluesky.utils import MsgGenerator

from dodal.common import inject
from mx_bluesky.common.utils.log import setup_hyperion_blueapi_logging
from mx_bluesky.hyperion.blueapi.in_process import (
    clean_up_udc,
    load_centre_collect,
    move_to_udc_default_state,
    robot_unload,
)
from mx_bluesky.hyperion.blueapi.parameters import (
    LoadCentreCollectParams,
)
from mx_bluesky.hyperion.experiment_plans.load_centre_collect_full_plan import (
    LoadCentreCollectComposite,
)
from mx_bluesky.hyperion.experiment_plans.robot_load_then_centre_plan import RobotLoadThenCentreComposite
from mx_bluesky.hyperion.experiment_plans.robot_load_then_centre_plan import \
    robot_load_then_xray_centre as _robot_load_then_xray_centre
from mx_bluesky.hyperion.experiment_plans.udc_default_state import UDCDefaultDevices
from mx_bluesky.hyperion.experiment_plans.udc_default_state import (
    UDCDefaultDevices,
)
from mx_bluesky.hyperion.parameters.constants import CONST
from mx_bluesky.hyperion.parameters.robot_load import RobotLoadThenCentre

__all__ = [
    "LoadCentreCollectComposite",
    "LoadCentreCollectParams",
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


def robot_load_and_xray_centre(
    parameters: RobotLoadThenCentre,
    composite: RobotLoadThenCentreComposite = inject()
) -> MsgGenerator:
    """Perform a robot load of the specified sample if it is not already loaded,
    then perform optical pin tip and grid detection followed by xray-centring.
    Move the smargon current position to the best detected centre if one is found.
    Generate ISPyB data collections for robot load and gridscans.
    """
    @set_run_key_decorator(CONST.PLAN.LOAD_CENTRE_COLLECT)
    @run_decorator(
        md={
            "metadata": {
                "sample_id": parameters.sample_id,
                "visit": parameters.visit,
                "container": parameters.sample_puck,
            },
            "activate_callbacks": [
                "BeamDrawingCallback",
                "SampleHandlingCallback",
            ],
            "with_snapshot": parameters.model_dump_json(
                include=WithSnapshot.model_fields.keys()  # type: ignore
            ),
        }
    )
    def decorated_plan():
        yield from _robot_load_then_xray_centre(composite, parameters)

    yield from decorated_plan()