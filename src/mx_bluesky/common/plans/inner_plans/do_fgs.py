from collections.abc import Callable
from time import time

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
from bluesky.utils import MsgGenerator
from dodal.devices.eiger import EigerDetector
from dodal.devices.fast_grid_scan import FastGridScanCommon
from dodal.devices.synchrotron import Synchrotron
from dodal.devices.zocalo.zocalo_results import (
    ZOCALO_STAGE_GROUP,
)
from dodal.log import LOGGER
from dodal.plan_stubs.check_topup import check_topup_and_wait_if_necessary
from scanspec.core import AxesPoints, Axis

from mx_bluesky.common.parameters.constants import (
    PlanNameConstants,
)
from mx_bluesky.common.plans.read_hardware import read_hardware_for_zocalo
from mx_bluesky.common.utils.tracing import TRACER


def _wait_for_zocalo_to_stage_then_do_fgs(
    grid_scan_device: FastGridScanCommon,
    detector: EigerDetector,
    synchrotron: Synchrotron,
    during_collection_plan: Callable[[], MsgGenerator] | None = None,
):
    expected_images = yield from bps.rd(grid_scan_device.expected_images)
    exposure_sec_per_image = yield from bps.rd(detector.cam.acquire_time)  # type: ignore # Fix types in ophyd-async (https://github.com/DiamondLightSource/mx-bluesky/issues/855)
    LOGGER.info("waiting for topup if necessary...")
    yield from check_topup_and_wait_if_necessary(
        synchrotron,
        expected_images * exposure_sec_per_image,
        30.0,
    )

    # Make sure ZocaloResults queue is clear and ready to accept our new data. Zocalo MUST
    # have been staged using ZOCALO_STAGE_GROUP prior to this
    LOGGER.info("Waiting for Zocalo device queue to have been cleared...")
    yield from bps.wait(ZOCALO_STAGE_GROUP)

    # Triggers Zocalo if RE is subscribed to ZocaloCallback
    yield from read_hardware_for_zocalo(detector)
    LOGGER.info("Wait for all moves with no assigned group")
    yield from bps.wait()

    LOGGER.info("kicking off FGS")
    yield from bps.kickoff(grid_scan_device, wait=True)
    gridscan_start_time = time()
    if during_collection_plan:
        yield from during_collection_plan()
    LOGGER.info("completing FGS")
    yield from bps.complete(grid_scan_device, wait=True)
    # Remove this logging statement once metrics have been added
    LOGGER.info(
        f"Grid scan motion program took {round(time() - gridscan_start_time, 2)} to complete"
    )


def kickoff_and_complete_gridscan(
    gridscan: FastGridScanCommon,
    detector: EigerDetector,  # Once Eiger inherits from StandardDetector, use that type instead
    synchrotron: Synchrotron,
    scan_points: list[AxesPoints[Axis]],
    scan_start_indices: list[int],
    plan_during_collection: Callable[[], MsgGenerator] | None = None,
):
    """Triggers a grid scan motion program and waits for completion, accounting for synchrotron topup.
    If the RunEngine is subscribed to ZocaloCallback, this plan will also trigger Zocalo.

    Can be used for multiple successive grid scans, see Hyperion's usage

    Args:
        gridscan (FastGridScanCommon):          Device which can trigger a fast grid scan and wait for completion
        detector (EigerDetector)                Detector device
        synchrotron (Synchrotron):              Synchrotron device
        scan_points (list[AxesPoints[Axis]]):   Each element in the list contains all the grid points for that grid scan.
                                                Two elements in this list indicates that two grid scans will be done, eg for Hyperion's 3D grid scans.
        scan_start_indices (list[int]):         Contains the first index of each grid scan
        plan_during_collection (Optional, MsgGenerator): Generic plan called in between kickoff and completion,
                                                eg waiting on zocalo.
    """

    assert len(scan_points) == len(scan_start_indices), (
        "scan_points and scan_start_indices must be lists of the same length!"
    )

    plan_name = PlanNameConstants.DO_FGS

    @TRACER.start_as_current_span(plan_name)
    @bpp.set_run_key_decorator(plan_name)
    @bpp.run_decorator(
        md={
            "subplan_name": plan_name,
            "scan_points": scan_points,
            "scan_start_indices": scan_start_indices,
        }
    )
    @bpp.contingency_decorator(
        except_plan=lambda e: (yield from bps.stop(detector)),  # type: ignore # Fix types in ophyd-async (https://github.com/DiamondLightSource/mx-bluesky/issues/855)
        else_plan=lambda: (yield from bps.unstage(detector)),
    )
    def _decorated_do_fgs():
        yield from _wait_for_zocalo_to_stage_then_do_fgs(
            gridscan,
            detector,
            synchrotron,
            during_collection_plan=plan_during_collection,
        )

    yield from _decorated_do_fgs()
