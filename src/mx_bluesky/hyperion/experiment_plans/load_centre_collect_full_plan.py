from __future__ import annotations

from collections.abc import Generator

import numpy as np
import pydantic
from blueapi.core import BlueskyContext
from bluesky.preprocessors import run_decorator, set_run_key_decorator, subs_wrapper
from bluesky.utils import MsgGenerator
from dodal.common.beamlines.beamline_utils import get_config_client
from dodal.devices.baton import Baton
from dodal.devices.oav.oav_parameters import OAVParameters

from mx_bluesky.common.parameters.components import AperturePolicy, WithSnapshot
from mx_bluesky.common.parameters.rotation import (
    RotationScanPerSweep,
)
from mx_bluesky.common.utils.aperture_selection import select_aperture_for_bbox_mm
from mx_bluesky.common.utils.context import device_composite_from_context
from mx_bluesky.common.utils.exceptions import CrystalNotFoundError
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.common.utils.xrc_result import XRayCentreEventHandler, XRayCentreResult
from mx_bluesky.hyperion.experiment_plans.robot_load_then_centre_plan import (
    RobotLoadThenCentreComposite,
    robot_load_then_xray_centre,
)
from mx_bluesky.hyperion.experiment_plans.rotation_scan_plan import (
    RotationScan,
    RotationScanComposite,
    rotation_scan_internal,
)
from mx_bluesky.hyperion.parameters.constants import CONST, I03Constants
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect
from mx_bluesky.hyperion.utils.centre_selection import samples_and_hits_to_collect


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
    LOGGER.info(
        f"aperture from parameters ROBOT LOAD is {parameters.robot_load_then_centre.selected_aperture}"
    )
    LOGGER.info(
        f"aperture from parameters ROTATION is {parameters.multi_rotation_scan.selected_aperture}"
    )
    if not oav_params:
        oav_params = OAVParameters(get_config_client(), context="xrayCentring")
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
        except CrystalNotFoundError:
            if parameters.select_centres.ignore_xtal_not_found:
                LOGGER.info("Ignoring crystal not found due to parameter settings.")
            else:
                raise

        sample_ids_and_hits = yield from (
            samples_and_hits_to_collect(
                parameters.select_centres,
                composite.gonio,
                parameters.sample_id,
                flyscan_event_handler.xray_centre_results,
            )
        )
        sample_ids_and_hits.sort(key=_x_coordinate)

        multi_rotation = parameters.multi_rotation_scan
        _update_aperture_selection(multi_rotation, sample_ids_and_hits)
        rotation_template = multi_rotation.rotation_scans.copy()

        multi_rotation.rotation_scans.clear()

        is_alternating = I03Constants.ALTERNATE_ROTATION_DIRECTION

        generator = rotation_scan_generator(is_alternating)
        next(generator)
        for sample_id, xray_centre_result in sample_ids_and_hits:
            for rot in rotation_template:
                combination = generator.send(
                    (rot, xray_centre_result.centre_of_mass_mm * 1000, sample_id)
                )
                multi_rotation.rotation_scans.append(combination)
        multi_rotation = RotationScan.model_validate(multi_rotation)

        assert (
            multi_rotation.demand_energy_ev
            == parameters.robot_load_then_centre.demand_energy_ev
        ), "Setting a different energy for gridscan and rotation is not supported"
        yield from rotation_scan_internal(composite, multi_rotation, oav_params)

    yield from plan_with_callback_subs()


def _update_aperture_selection(
    multi_rotation_scan: RotationScan,
    sample_ids_and_hits: list[tuple[int, XRayCentreResult]],
):
    """Select aperture if auto selection is specified. If more than one crystal is found (i.e. multipin),
    select the large aperture, otherwise select based on crystal dimensions."""
    assert len(sample_ids_and_hits) > 0
    if multi_rotation_scan.selected_aperture == AperturePolicy.AUTO:
        if len(sample_ids_and_hits) > 1:
            multi_rotation_scan.selected_aperture = AperturePolicy.LARGE
        else:
            first_hit = sample_ids_and_hits[0][1]
            bbox_size = first_hit.bounding_box_mm[1] - first_hit.bounding_box_mm[0]
            multi_rotation_scan.selected_aperture = select_aperture_for_bbox_mm(
                bbox_size, I03Constants.APERTURE_SELECTION_XTAL_WIDTH_THRESHOLD_MM
            )


def _x_coordinate(
    sample_id_and_xrc_result: tuple[int, XRayCentreResult],
) -> float:
    location = sample_id_and_xrc_result[1].centre_of_mass_mm
    return location[0]  # type: ignore


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
