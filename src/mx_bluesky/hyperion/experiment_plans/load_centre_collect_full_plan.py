from __future__ import annotations

from collections.abc import Generator

import bluesky.plan_stubs as bps
import numpy as np
import pydantic
from blueapi.core import BlueskyContext
from bluesky.preprocessors import run_decorator, set_run_key_decorator, subs_wrapper
from bluesky.utils import MsgGenerator
from dodal.devices.baton import Baton
from dodal.devices.oav.oav_parameters import OAVParameters

import mx_bluesky.common.xrc_result as flyscan_result
from mx_bluesky.common.parameters.components import WithSnapshot
from mx_bluesky.common.parameters.rotation import (
    RotationScanPerSweep,
)
from mx_bluesky.common.utils.context import device_composite_from_context
from mx_bluesky.common.utils.exceptions import CrystalNotFoundException
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.common.xrc_result import XRayCentreEventHandler
from mx_bluesky.hyperion.experiment_plans.robot_load_then_centre_plan import (
    RobotLoadThenCentreComposite,
    robot_load_then_xray_centre,
)
from mx_bluesky.hyperion.experiment_plans.rotation_scan_plan import (
    RotationScan,
    RotationScanComposite,
    rotation_scan_internal,
)
from mx_bluesky.hyperion.external_interaction.config_server import (
    get_hyperion_config_client,
)
from mx_bluesky.hyperion.parameters.constants import CONST, I03Constants
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class LoadCentreCollectComposite(RobotLoadThenCentreComposite, RotationScanComposite):
    """Composite that provides access to the required devices."""

    baton: Baton


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
    * If X-ray centring finds one or more diffracting centres then for each centre
     that satisfies the chosen selection function,
     move to that centre and do a collection with the specified parameters.
    """

    get_hyperion_config_client().refresh_cache()

    if not oav_params:
        oav_params = OAVParameters(context="xrayCentring")
    oav_config_file = oav_params.oav_config_json

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
                "AlertOnContainerChange",
            ],
            "with_snapshot": parameters.multi_rotation_scan.model_dump_json(
                include=WithSnapshot.model_fields.keys()  # type: ignore
            ),
        }
    )
    def plan_with_callback_subs():
        flyscan_event_handler = XRayCentreEventHandler()
        try:
            yield from subs_wrapper(
                robot_load_then_xray_centre(
                    composite, parameters.robot_load_then_centre, oav_config_file
                ),
                flyscan_event_handler,
            )
        except CrystalNotFoundException:
            if parameters.select_centres.ignore_xtal_not_found:
                LOGGER.info("Ignoring crystal not found due to parameter settings.")
            else:
                raise

        locations_to_collect_um: list[np.ndarray]
        samples_to_collect: list[int]

        if flyscan_event_handler.xray_centre_results:
            selection_func = flyscan_result.resolve_selection_fn(
                parameters.selection_params
            )
            hits = selection_func(flyscan_event_handler.xray_centre_results)
            hits_to_collect = []
            for hit in hits:
                if hit.sample_id is None:
                    LOGGER.warning(
                        f"Diffracting centre {hit} not collected because no sample id was assigned."
                    )
                else:
                    hits_to_collect.append(hit)

            locations_to_collect_um = [
                hit.centre_of_mass_mm * 1000 for hit in hits_to_collect
            ]
            samples_to_collect = [hit.sample_id for hit in hits_to_collect]
            LOGGER.info(
                f"Selected hits {hits_to_collect} using {selection_func}, args={parameters.selection_params}"
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
            samples_to_collect = [parameters.sample_id]

        multi_rotation = parameters.multi_rotation_scan
        rotation_template = multi_rotation.rotation_scans.copy()

        multi_rotation.rotation_scans.clear()

        is_alternating = I03Constants.ALTERNATE_ROTATION_DIRECTION

        generator = rotation_scan_generator(is_alternating)
        next(generator)
        for location, sample_id in zip(
            locations_to_collect_um, samples_to_collect, strict=True
        ):
            for rot in rotation_template:
                combination = generator.send((rot, location, sample_id))
                multi_rotation.rotation_scans.append(combination)
        multi_rotation = RotationScan.model_validate(multi_rotation)

        assert (
            multi_rotation.demand_energy_ev
            == parameters.robot_load_then_centre.demand_energy_ev
        ), "Setting a different energy for gridscan and rotation is not supported"
        yield from rotation_scan_internal(composite, multi_rotation, oav_params)

    yield from plan_with_callback_subs()


def rotation_scan_generator(
    is_alternating: bool,
) -> Generator[
    RotationScanPerSweep, tuple[RotationScanPerSweep, np.ndarray, int], None
]:
    scan_template, location, sample_id = yield  # type: ignore
    next_rotation_direction = scan_template.rotation_direction
    while True:
        scan = scan_template.model_copy()
        (
            scan.x_start_um,
            scan.y_start_um,
            scan.z_start_um,
        ) = location
        scan.sample_id = sample_id
        if is_alternating:
            if next_rotation_direction != scan.rotation_direction:
                # If originally specified direction of the current scan is different
                # from that required, swap the start and ends.
                start = scan.omega_start_deg
                rotation_sign = scan.rotation_direction.multiplier
                end = start + rotation_sign * scan.scan_width_deg
                scan.omega_start_deg = end
                scan.rotation_direction = next_rotation_direction
            next_rotation_direction = next_rotation_direction.opposite

        scan_template, location, sample_id = yield scan
