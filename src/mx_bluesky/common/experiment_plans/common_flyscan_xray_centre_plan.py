from __future__ import annotations

from typing import Any, TypeVar

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
from bluesky.utils import FailedStatus, MsgGenerator
from dodal.devices.detector import DetectorParams
from dodal.devices.fast_grid_scan import (
    FastGridScanThreeD,
    GridScanInvalidError,
)

from mx_bluesky.common.device_setup_plans.detector.beamline_specific import (
    TDiffractionEssentialDevices,
)
from mx_bluesky.common.device_setup_plans.gridscan.beamline_specific import (
    BeamlineSpecificFGSFeatures,
)
from mx_bluesky.common.experiment_plans.inner_plans.do_fgs import (
    kickoff_and_complete_gridscan,
)
from mx_bluesky.common.parameters.components import (
    DiffractionExperimentWithSample,
)
from mx_bluesky.common.parameters.constants import (
    PlanGroupCheckpointConstants,
    PlanNameConstants,
)
from mx_bluesky.common.parameters.gridscan import (
    GridScanParams,
)
from mx_bluesky.common.utils.exceptions import (
    SampleError,
)
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.common.utils.tracing import TRACER

TParameters = TypeVar("TParameters", bound=DiffractionExperimentWithSample)


def common_flyscan_xray_centre(
    composite: TDiffractionEssentialDevices,
    parameters: TParameters,
    xrc_detector_params: DetectorParams,
    grid_scan_parameters: GridScanParams,
    beamline_specific: BeamlineSpecificFGSFeatures[
        TDiffractionEssentialDevices, TParameters
    ],
) -> MsgGenerator:
    """Main entry point of the MX-Bluesky x-ray centering flyscan

    Args:
        composite (TDiffractionEssentialDevices): Devices required to perform this plan.

        xrc_detector_params (DetectorParams): Detector parameters to use during x-ray centring.
        parameters (SpecifiedThreeDGridScan): Parameters required to perform this plan.
        grid_scan_parameters (GridScanParams): Parameters defining the grid scan(s) to be carried out.

        beamline_specific (BeamlineSpecificFGSFeatures): Configure the beamline-specific version
        of this plan: For example triggering setup and tidy up plans, as well as what to do with the
        centering results.

    With a minimum set of devices and parameters, prepares for; performs; and tidies up a flyscan
    x-ray-center plan. This includes: Configuring desired triggering; writing nexus files; triggering zocalo;
    reading hardware before and during the scan; and tidying up devices after
    the plan is complete. Optionally fetch results from zocalo after completing the grid scan.

    This plan will also push data to ispyb when used with the ispyb_activation_decorator.

    There are a few other useful decorators to use with this plan, see: verify_undulator_gap_before_run_decorator, common/preprocessors/preprocessors.py
    """

    def _overall_tidy():
        yield from beamline_specific.tidy_plan(composite)
        yield from beamline_specific.tidy_detector_plan(composite)

    def _decorated_flyscan():
        @bpp.set_run_key_decorator(PlanNameConstants.GRIDSCAN_OUTER)
        @bpp.run_decorator(  # attach experiment metadata to the start document
            md={
                "subplan_name": PlanNameConstants.GRIDSCAN_OUTER,
                "mx_bluesky_parameters": parameters.model_dump_json(),
                "detector_params": xrc_detector_params.model_dump_json(),
                "grid_scan_parameters": grid_scan_parameters.model_dump_json(),
                "activate_callbacks": [
                    "GridscanNexusFileCallback",
                ],
            }
        )
        @bpp.finalize_decorator(lambda: _overall_tidy())
        def run_gridscan_and_tidy(
            fgs_composite: TDiffractionEssentialDevices,
        ) -> MsgGenerator:
            yield from beamline_specific.setup_trigger_plan(
                fgs_composite, parameters, grid_scan_parameters
            )

            LOGGER.info("Starting grid scan")
            yield from run_gridscan(
                fgs_composite,
                grid_scan_parameters,
                xrc_detector_params,
                beamline_specific,
            )

            LOGGER.info("Grid scan finished")

        yield from run_gridscan_and_tidy(composite)

    yield from _decorated_flyscan()


def run_gridscan(
    fgs_composite: TDiffractionEssentialDevices,
    grid_scan_params: GridScanParams,
    detector_params: DetectorParams,
    beamline_specific: BeamlineSpecificFGSFeatures[TDiffractionEssentialDevices, Any],
):
    with TRACER.start_span("moving_omega_to_0"):
        yield from bps.abs_set(
            fgs_composite.gonio.wrapped_omega.phase,
            grid_scan_params.omega_starts_deg[0],
            wait=True,
        )

    with TRACER.start_span("ispyb_hardware_readings"):
        yield from beamline_specific.read_pre_flyscan_plan()

    LOGGER.info("Setting fgs params")

    try:
        yield from beamline_specific.set_flyscan_params_plan(grid_scan_params)
    except FailedStatus as e:
        if isinstance(e.__cause__, GridScanInvalidError):
            raise SampleError(
                "Scan invalid - gridscan not valid for detected pin position"
            ) from e
        else:
            raise e

    LOGGER.info("Waiting for pre-arming to finish")
    yield from bps.wait(PlanGroupCheckpointConstants.GRID_READY_FOR_DC)

    yield from beamline_specific.arm_detector_plan(
        fgs_composite,
        detector_params,
        PlanGroupCheckpointConstants.GRIDSCAN_ARMING_COMPLETE,
    )
    LOGGER.info("Waiting for arming to finish")
    yield from bps.wait(PlanGroupCheckpointConstants.GRIDSCAN_ARMING_COMPLETE)

    yield from kickoff_and_complete_gridscan(
        beamline_specific,
        fgs_composite,
        grid_scan_params,
        detector_params,
        plan_during_collection=beamline_specific.read_during_collection_plan,
    )

    # GDA's 3D gridscans requires Z steps to be at 0, so make sure we leave this device
    # in a GDA-happy state.
    if isinstance(beamline_specific.fgs_motors, FastGridScanThreeD):
        yield from bps.abs_set(beamline_specific.fgs_motors.z_steps, 0, wait=False)
