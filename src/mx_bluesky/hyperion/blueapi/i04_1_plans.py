"""
This module is the bluesky plan module for use with hyperion-blueapi.
Importing this module will configure debug and info logging as a side-effect - so this module should not be
imported directly by other components as it is intended only as the entry-point for BlueAPI.
"""

import pydantic.dataclasses
from bluesky import plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.common import inject
from dodal.devices.robot import BartRobot

from mx_bluesky.beamlines.i04_1.beamsize.i04_1_aperture_scatterguard import (
    I04_1_ApertureScatterguardComposite,
    I04_1_BeamSizePlans,
)
from mx_bluesky.common.utils.log import setup_hyperion_blueapi_logging
from mx_bluesky.hyperion.blueapi.in_process import (
    clean_up_udc,
    move_to_udc_default_state,
    robot_unload,
)
from mx_bluesky.hyperion.blueapi.mixins import TopNByMaxCountSelection
from mx_bluesky.hyperion.blueapi.parameters import (
    LoadCentreCollectParams,
    load_centre_collect_to_internal,
    pin_tip_centre_then_xray_centre_to_internal,
)
from mx_bluesky.hyperion.experiment_plans.hyperion_beamline_specific import (
    construct_hyperion_specific_features,
)
from mx_bluesky.hyperion.experiment_plans.load_centre_collect_full_plan import (
    LoadCentreCollectComposite,
)
from mx_bluesky.hyperion.experiment_plans.load_centre_collect_full_plan import (
    load_centre_collect_full as _load_centre_collect_full,
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

from mx_bluesky.beamlines.phase1.beamsize.phase1_aperture_scatterguard import (
    Phase1ApertureScatterguardPlans,
)
from mx_bluesky.hyperion.blueapi.composites import (
    HyperionGridDetectThenXRayCentreComposite,
)


def _init_plan_module():
    """Initialisation hooks for hyperion-blueapi"""
    setup_hyperion_blueapi_logging(CONST.LOG_FILE_NAME)


_init_plan_module()


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class I04_1_LoadCentreCollectComposite(  # noqa: N801
    LoadCentreCollectComposite[I04_1_ApertureScatterguardComposite]
):
    @property
    def beamsize_composite(self) -> I04_1_ApertureScatterguardComposite:
        return self


def load_centre_collect(
    parameters: LoadCentreCollectParams,
    composite: I04_1_LoadCentreCollectComposite = inject(),
) -> MsgGenerator:
    """
    Attempt a complete data collection experiment, consisting of the following:
        * Load the sample if necessary
        * Move to the specified goniometer start angles
        * Perform optical centring, then X-ray centring
        * If X-ray centring finds one or more diffracting centres then for each centre
          that satisfies the chosen selection function,
          move to that centre and do a collection with the specified parameters.
    """
    yield from _load_centre_collect_full(
        composite,
        I04_1_BeamSizePlans(),
        load_centre_collect_to_internal(parameters),
    )


def pin_tip_centre_then_xray_centre(
    visit: str,
    storage_directory: str,
    composite: HyperionGridDetectThenXRayCentreComposite = inject(),
    robot: BartRobot = inject("robot"),
) -> MsgGenerator:
    """
    Run a commissioning pin-tip-detection and XRC, using the same settings as for hyperion UDC as far as
    is possible.
    Raises: CrystalNotFoundError if no crystal is found
    """
    sample_id = yield from bps.rd(robot.sample_id)
    sample_puck = yield from bps.rd(robot.current_puck)
    sample_pin = yield from bps.rd(robot.current_pin)

    internal_params = pin_tip_centre_then_xray_centre_to_internal(
        visit, storage_directory, sample_id, sample_puck, sample_pin
    )
    beamsize_device_plans = Phase1ApertureScatterguardPlans()
    beamline_specific = construct_hyperion_specific_features(
        composite, internal_params, beamsize_device_plans
    )

    yield from _pin_tip_centre_then_xray_centre(
        beamline_specific,
        composite,
        internal_params,
        TopNByMaxCountSelection(n=1),
        Phase1ApertureScatterguardPlans(),
    )
