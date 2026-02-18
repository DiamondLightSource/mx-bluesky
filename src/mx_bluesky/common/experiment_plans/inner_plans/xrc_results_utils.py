from __future__ import annotations

import dataclasses
from collections.abc import Sequence

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
import numpy as np
from bluesky.utils import MsgGenerator, make_decorator
from dodal.common.beamlines.commissioning_mode import read_commissioning_mode
from dodal.devices.zocalo.zocalo_results import (
    XrcResult,
    ZocaloResults,
    get_full_processing_results,
)

from mx_bluesky.common.experiment_plans.inner_plans.do_fgs import ZOCALO_STAGE_GROUP
from mx_bluesky.common.parameters.constants import (
    GridscanParamConstants,
    PlanNameConstants,
)
from mx_bluesky.common.parameters.gridscan import SpecifiedThreeDGridScan
from mx_bluesky.common.utils.exceptions import (
    CrystalNotFoundError,
)
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.common.utils.xrc_result import XRayCentreResult


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

    yield from bps.trigger(zocalo_results, wait=True)
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
        commissioning_mode = yield from read_commissioning_mode()
        if commissioning_mode:
            LOGGER.info("Commissioning mode enabled, returning dummy result")
            flyscan_results = [_generate_dummy_xrc_result(parameters)]
        else:
            LOGGER.warning("No X-ray centre received")
            raise CrystalNotFoundError()
    yield from _fire_xray_centre_result_event(flyscan_results)


def _generate_dummy_xrc_result(params: SpecifiedThreeDGridScan) -> XRayCentreResult:
    coms = []
    assert params.num_grids % 2 == 0, (
        "XRC results in commissioning mode currently only works for an even number of grids"
    )

    for grid in range(int(params.num_grids / 2)):
        # For even number of grids, Z steps are actually the even indexed y steps
        coms.append(
            [
                params.x_steps / 2,
                params.y_steps[2 * grid] / 2,
                params.y_steps[2 * grid + 1] / 2,
            ]
        )

    com = [sum(x) / len(x) for x in zip(*coms, strict=True)]  # Get average

    max_voxel = [round(p) for p in com]
    return _xrc_result_in_boxes_to_result_in_mm(
        XrcResult(
            centre_of_mass=com,
            max_voxel=max_voxel,
            bounding_box=[max_voxel, [p + 1 for p in max_voxel]],
            n_voxels=1,
            max_count=10000,
            total_count=100000,
            sample_id=params.sample_id,
        ),
        params,
    )


def _xrc_result_in_boxes_to_result_in_mm(
    xrc_result: XrcResult, parameters: SpecifiedThreeDGridScan
) -> XRayCentreResult:
    fgs_params = parameters.fast_gridscan_params
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


# Remove after https://github.com/bluesky/bluesky/issues/1979
def _zocalo_stage_wrapper(plan: MsgGenerator, zocalo: ZocaloResults):
    yield from bps.stage(zocalo, group=ZOCALO_STAGE_GROUP)
    yield from bpp.contingency_wrapper(
        plan, final_plan=lambda: (yield from bps.unstage(zocalo))
    )


zocalo_stage_decorator = make_decorator(_zocalo_stage_wrapper)
