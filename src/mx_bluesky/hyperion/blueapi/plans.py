"""
This module is the bluesky plan module for use with hyperion-blueapi.
Importing this module will configure debug and info logging as a side-effect - so this module should not be
imported directly by other components as it is intended only as the entry-point for BlueAPI.
"""

from bluesky import plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.common import inject

from mx_bluesky.common.utils.log import setup_hyperion_blueapi_logging
from mx_bluesky.hyperion.blueapi.in_process import (
    clean_up_udc,
    load_centre_collect,
    move_to_udc_default_state,
    robot_unload,
)
from mx_bluesky.hyperion.blueapi.mixins import TopNByMaxCountSelection
from mx_bluesky.hyperion.blueapi.parameters import (
    LoadCentreCollectParams,
    pin_tip_centre_then_xray_centre_to_internal,
)
from mx_bluesky.hyperion.experiment_plans.load_centre_collect_full_plan import (
    LoadCentreCollectComposite,
)
from mx_bluesky.hyperion.experiment_plans.pin_centre_then_xray_centre import (
    pin_tip_centre_then_xray_centre as _pin_tip_centre_then_xray_centre,
)
from mx_bluesky.hyperion.experiment_plans.udc_default_state import UDCDefaultDevices
from mx_bluesky.hyperion.parameters.constants import CONST

__all__ = [
    "LoadCentreCollectComposite",
    "LoadCentreCollectParams",
    "UDCDefaultDevices",
    "clean_up_udc",
    "load_centre_collect",
    "move_to_udc_default_state",
    "pin_tip_centre_then_xray_centre",
    "robot_unload",
]

from mx_bluesky.hyperion.parameters.device_composites import (
    HyperionGridDetectThenXRayCentreComposite,
)


def _init_plan_module():
    """Initialisation hooks for hyperion-blueapi"""
    setup_hyperion_blueapi_logging(CONST.LOG_FILE_NAME)


_init_plan_module()


def pin_tip_centre_then_xray_centre(
    visit: str,
    storage_directory: str,
    composite: HyperionGridDetectThenXRayCentreComposite = inject(),
) -> MsgGenerator:
    """
    Run a commissioning pin-tip-detection and XRC, using the same settings as for hyperion UDC as far as
    is possible.
    Raises: CrystalNotFoundError if no crystal is found
    """
    sample_id = yield from bps.rd(composite.robot.sample_id)
    sample_puck = yield from bps.rd(composite.robot.current_puck)
    sample_pin = yield from bps.rd(composite.robot.current_pin)

    internal_params = pin_tip_centre_then_xray_centre_to_internal(
        visit, storage_directory, sample_id, sample_puck, sample_pin
    )
    yield from _pin_tip_centre_then_xray_centre(
        composite, internal_params, TopNByMaxCountSelection(n=1)
    )
