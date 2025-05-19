from __future__ import annotations

import bluesky.plan_stubs as bps
import numpy as np
import pydantic
from blueapi.core import BlueskyContext
from bluesky.preprocessors import run_decorator, set_run_key_decorator, subs_wrapper
from bluesky.utils import MsgGenerator
from dodal.devices.oav.oav_parameters import OAVParameters

import mx_bluesky.common.xrc_result as flyscan_result
from mx_bluesky.common.parameters.components import WithSnapshot
from mx_bluesky.common.utils.context import device_composite_from_context
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.common.xrc_result import XRayCentreEventHandler
from mx_bluesky.hyperion.experiment_plans.robot_load_then_centre_plan import (
    RobotLoadThenCentreComposite,
    robot_load_then_xray_centre,
)
from mx_bluesky.hyperion.experiment_plans.rotation_scan_plan import (
    MultiRotationScan,
    RotationScanComposite,
    multi_rotation_scan_internal,
)
from mx_bluesky.hyperion.parameters.constants import CONST
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class LoadCentreCollectComposite(RobotLoadThenCentreComposite, RotationScanComposite):
    """Composite that provides access to the required devices."""


def create_devices(context: BlueskyContext) -> LoadCentreCollectComposite:
    """Create the necessary devices for the plan."""
    return device_composite_from_context(context, LoadCentreCollectComposite)


def load_centre_collect_full(
    composite: LoadCentreCollectComposite,
    parameters: LoadCentreCollect,
    oav_params: OAVParameters | None = None,
) -> MsgGenerator:
    """Attempt a complete data collection experiment, consisting of the following:
    * Load the sample if necessary
    * Move to the specified goniometer start angles
    * Perform optical centring, then X-ray centring
    * If X-ray centring finds a diffracting centre then move to that centre and
    * do a collection with the specified parameters.
    """
    if not oav_params:
        oav_params = OAVParameters(context="xrayCentring")
    oav_config_file = oav_params.oav_config_json

    @set_run_key_decorator(CONST.PLAN.LOAD_CENTRE_COLLECT)
    @run_decorator(
        md={
            "metadata": {"sample_id": parameters.sample_id},
            "activate_callbacks": ["BeamDrawingCallback", "SampleHandlingCallback"],
            "with_snapshot": parameters.multi_rotation_scan.model_dump_json(
                include=WithSnapshot.model_fields.keys()  # type: ignore
            ),
        }
    )
    def plan_with_callback_subs():
        flyscan_event_handler = XRayCentreEventHandler()
        yield from subs_wrapper(
            robot_load_then_xray_centre(
                composite, parameters.robot_load_then_centre, oav_config_file
            ),
            flyscan_event_handler,
        )

        locations_to_collect_um: list[np.ndarray] = []

        if flyscan_event_handler.xray_centre_results:
            selection_func = flyscan_result.resolve_selection_fn(
                parameters.selection_params
            )
            hits = selection_func(flyscan_event_handler.xray_centre_results)
            locations_to_collect_um = [hit.centre_of_mass_mm * 1000 for hit in hits]

            LOGGER.info(
                f"Selected hits {hits} using {selection_func}, args={parameters.selection_params}"
            )
        else:
            # If the xray centring hasn't found a result but has not thrown an error it
            # means that we do not need to recentre and can collect where we are
            initial_x_mm = yield from bps.rd(composite.smargon.x.user_readback)
            initial_y_mm = yield from bps.rd(composite.smargon.y.user_readback)
            initial_z_mm = yield from bps.rd(composite.smargon.z.user_readback)

            locations_to_collect_um = [
                np.array([initial_x_mm, initial_y_mm, initial_z_mm]) * 1000
            ]

        multi_rotation = parameters.multi_rotation_scan
        rotation_template = multi_rotation.rotation_scans.copy()

        multi_rotation.rotation_scans.clear()

        for location in locations_to_collect_um:
            for rot in rotation_template:
                combination = rot.model_copy()
                (
                    combination.x_start_um,
                    combination.y_start_um,
                    combination.z_start_um,
                ) = location
                multi_rotation.rotation_scans.append(combination)
        multi_rotation = MultiRotationScan.model_validate(multi_rotation)

        assert (
            multi_rotation.demand_energy_ev
            == parameters.robot_load_then_centre.demand_energy_ev
        ), "Setting a different energy for gridscan and rotation is not supported"
        yield from multi_rotation_scan_internal(composite, multi_rotation, oav_params)

    yield from plan_with_callback_subs()
