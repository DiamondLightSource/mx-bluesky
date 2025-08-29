from __future__ import annotations

import dataclasses
from collections.abc import Sequence

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
import numpy as np
from bluesky.utils import MsgGenerator
from dodal.devices.zocalo import ZocaloResults
from dodal.devices.zocalo.zocalo_results import (
    XrcResult,
    get_full_processing_results,
)

from mx_bluesky.common.parameters.constants import (
    GridscanParamConstants,
    PlanNameConstants,
)
from mx_bluesky.common.parameters.gridscan import SpecifiedThreeDGridScan
from mx_bluesky.common.utils.exceptions import (
    CrystalNotFoundException,
)
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.common.xrc_result import XRayCentreResult


def fetch_xrc_results_from_zocalo(
    zocalo_results: ZocaloResults,
    parameters: SpecifiedThreeDGridScan,
) -> MsgGenerator:
    """
    Get XRC results from the ZocaloResults device which was staged during a grid scan,
    and store them in XRayCentreEventHandler.xray_centre_results by firing an event.

    The RunEngine must be subscribed to XRayCentreEventHandler for this plan to work.
    """

    LOGGER.info("Getting X-ray center Zocalo results...")

    yield from bps.trigger(zocalo_results)
    LOGGER.info("Zocalo triggered and read, interpreting results.")
    xrc_results = yield from get_full_processing_results(zocalo_results)
    LOGGER.info(f"Got xray centres, top 5: {xrc_results[:5]}")
    filtered_results = [
        result
        for result in xrc_results
        if result["total_count"]
        >= GridscanParamConstants.ZOCALO_MIN_TOTAL_COUNT_THRESHOLD
    ]
    discarded_count = len(xrc_results) - len(filtered_results)
    if discarded_count > 0:
        LOGGER.info(f"Removed {discarded_count} results because below threshold")
    if filtered_results:
        flyscan_results = [
            _xrc_result_in_boxes_to_result_in_mm(xr, parameters)
            for xr in filtered_results
        ]
    else:
        LOGGER.warning("No X-ray centre received")
        raise CrystalNotFoundException()
    yield from _fire_xray_centre_result_event(flyscan_results)


def _xrc_result_in_boxes_to_result_in_mm(
    xrc_result: XrcResult, parameters: SpecifiedThreeDGridScan
) -> XRayCentreResult:
    fgs_params = parameters.FGS_params
    xray_centre = fgs_params.grid_position_to_motor_position(
        np.array(xrc_result["centre_of_mass"])
    )
    # A correction is applied to the bounding box to map discrete grid coordinates to
    # the corners of the box in motor-space; we do not apply this correction
    # to the xray-centre as it is already in continuous space and the conversion has
    # been performed already
    # In other words, xrc_result["bounding_box"] contains the position of the box centre,
    # so we subtract half a box to get the corner of the box
    return XRayCentreResult(
        centre_of_mass_mm=xray_centre,
        bounding_box_mm=(
            fgs_params.grid_position_to_motor_position(
                np.array(xrc_result["bounding_box"][0]) - 0.5
            ),
            fgs_params.grid_position_to_motor_position(
                np.array(xrc_result["bounding_box"][1]) - 0.5
            ),
        ),
        max_count=xrc_result["max_count"],
        total_count=xrc_result["total_count"],
        sample_id=xrc_result["sample_id"],
    )


def _fire_xray_centre_result_event(results: Sequence[XRayCentreResult]):
    def empty_plan():
        return iter([])

    yield from bpp.set_run_key_wrapper(
        bpp.run_wrapper(
            empty_plan(),
            md={
                PlanNameConstants.FLYSCAN_RESULTS: [
                    dataclasses.asdict(r) for r in results
                ]
            },
        ),
        PlanNameConstants.FLYSCAN_RESULTS,
    )
