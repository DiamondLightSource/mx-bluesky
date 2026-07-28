from collections.abc import Callable
from time import time

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
from bluesky.utils import MsgGenerator
from dodal.devices.detector import DetectorParams
from dodal.devices.synchrotron import Synchrotron
from dodal.devices.zocalo.zocalo_results import (
    ZOCALO_STAGE_GROUP,
)
from dodal.log import LOGGER
from dodal.plan_stubs.check_topup import check_topup_and_wait_if_necessary

from mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan import (
    BeamlineSpecificFGSFeatures,
)
from mx_bluesky.common.experiment_plans.inner_plans.read_hardware import (
    read_hardware_for_zocalo,
)
from mx_bluesky.common.parameters.constants import (
    PlanNameConstants,
)
from mx_bluesky.common.parameters.device_composites import DiffractionEssentialDevices
from mx_bluesky.common.parameters.gridscan import GridScanParams
from mx_bluesky.common.utils.tracing import TRACER


def _wait_for_zocalo_to_stage_then_do_fgs(
    beamline_specific: BeamlineSpecificFGSFeatures,
    grid_scan_params: GridScanParams,
    detector_params: DetectorParams,
    synchrotron: Synchrotron,
    during_collection_plan: Callable[[], MsgGenerator] | None = None,
):
    LOGGER.info("waiting for topup if necessary...")
    yield from check_topup_and_wait_if_necessary(
        synchrotron,
        grid_scan_params.num_images * detector_params.exposure_time_s,
        30.0,
    )

    # If using ZocaloResults device, make sure ZocaloResults queue is clear and
    # ready to accept our new data. Zocalo MUST have been staged using ZOCALO_STAGE_GROUP prior to this
    yield from bps.wait(ZOCALO_STAGE_GROUP)

    # Triggers Zocalo if run_engine is subscribed to ZocaloCallback
    yield from read_hardware_for_zocalo(beamline_specific)
    LOGGER.info("Wait for all moves with no assigned group")
    yield from bps.wait()

    LOGGER.info("kicking off FGS")
    yield from bps.kickoff(beamline_specific.fgs_motors, wait=True)
    gridscan_start_time = time()
    if during_collection_plan:
        yield from during_collection_plan()
    LOGGER.info("completing FGS")
    yield from bps.complete(beamline_specific.fgs_motors, wait=True)
    # Remove this logging statement once metrics have been added
    LOGGER.info(
        f"Grid scan motion program took {round(time() - gridscan_start_time, 2)} to complete"
    )


def kickoff_and_complete_gridscan(
    beamline_specific: BeamlineSpecificFGSFeatures,
    device_composite: DiffractionEssentialDevices,
    grid_scan_params: GridScanParams,
    detector_params: DetectorParams,
    plan_during_collection: Callable[[], MsgGenerator] | None = None,
):
    """Triggers a grid scan motion program and waits for completion, accounting for synchrotron topup.
    If the RunEngine is subscribed to ZocaloCallback, this plan will also trigger Zocalo.

    Can be used for multiple successive grid scans, see Hyperion's usage

    Args:
        beamline_specific (BeamlineSpecificFGSFeatures):    Beamline specific gridscan plans and devices
        device_composite (DiffractionEssentialDevices): Composite container necessary devices
        grid_scan_params (GridScanParams):      Parameters for the grid scan
        detector_params (DetectorParams):       Detector parameters
        plan_during_collection (Optional, MsgGenerator): Generic plan called in between kickoff and completion,
                                                eg waiting on zocalo.
    """

    plan_name = PlanNameConstants.DO_FGS
    omega_starts_deg = grid_scan_params.omega_starts_deg

    @TRACER.start_as_current_span(plan_name)
    @bpp.set_run_key_decorator(plan_name)
    @bpp.run_decorator(
        md={
            "subplan_name": plan_name,
            "omega_to_scan_spec": {
                # These have to be cast to strings due to a bug in orsjon. See
                # https://github.com/ijl/orjson/issues/414
                # See https://github.com/DiamondLightSource/mx-bluesky/issues/1631 regarding integer cast
                str(int(omega_starts_deg[i])): grid_scan_params.scan_points[i]
                for i in range(len(omega_starts_deg))
            },
        }
    )
    @bpp.contingency_decorator(
        except_plan=lambda e: (yield from bps.stop(detector)),  # type: ignore # Fix types in ophyd-async (https://github.com/DiamondLightSource/mx-bluesky/issues/855)
        else_plan=lambda: (
            yield from beamline_specific.disarm_detector_plan(device_composite)
        ),
    )
    def _decorated_do_fgs():
        yield from _wait_for_zocalo_to_stage_then_do_fgs(
            beamline_specific,
            grid_scan_params,
            detector_params,
            device_composite.synchrotron,
            during_collection_plan=plan_during_collection,
        )

    yield from _decorated_do_fgs()
