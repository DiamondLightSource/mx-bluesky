from __future__ import annotations

import dataclasses
from collections.abc import Callable, Sequence
from functools import partial

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
import numpy as np
import pydantic
from bluesky.protocols import Readable
from bluesky.utils import MsgGenerator
from dodal.devices.eiger import EigerDetector
from dodal.devices.fast_grid_scan import (
    FastGridScanCommon,
)
from dodal.devices.smargon import Smargon
from dodal.devices.synchrotron import Synchrotron
from dodal.devices.zocalo import ZocaloResults
from dodal.devices.zocalo.zocalo_results import (
    XrcResult,
    get_full_processing_results,
)

from mx_bluesky.common.parameters.constants import (
    DocDescriptorNames,
    GridscanParamConstants,
    PlanGroupCheckpointConstants,
    PlanNameConstants,
)
from mx_bluesky.common.parameters.gridscan import SpecifiedThreeDGridScan
from mx_bluesky.common.plans.inner_plans.do_fgs import (
    ZOCALO_STAGE_GROUP,
    kickoff_and_complete_gridscan,
)
from mx_bluesky.common.plans.read_hardware import (
    read_hardware_plan,
)
from mx_bluesky.common.utils.exceptions import (
    CrystalNotFoundException,
    SampleException,
)
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.common.utils.tracing import TRACER
from mx_bluesky.common.xrc_result import XRayCentreResult


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class FlyScanEssentialDevices:
    eiger: EigerDetector
    synchrotron: Synchrotron
    zocalo: ZocaloResults
    smargon: Smargon


@dataclasses.dataclass
class BeamlineSpecificFGSFeatures:
    setup_trigger_plan: Callable[..., MsgGenerator]
    tidy_plan: Callable[..., MsgGenerator]
    set_flyscan_params_plan: Callable[..., MsgGenerator]
    fgs_motors: FastGridScanCommon
    read_pre_flyscan_plan: Callable[
        ..., MsgGenerator
    ]  # Eventually replace with https://github.com/DiamondLightSource/mx-bluesky/issues/819
    read_during_collection_plan: Callable[..., MsgGenerator]
    get_xrc_results_from_zocalo: bool


def construct_beamline_specific_FGS_features(
    setup_trigger_plan: Callable[..., MsgGenerator],
    tidy_plan: Callable[..., MsgGenerator],
    set_flyscan_params_plan: Callable[..., MsgGenerator],
    fgs_motors: FastGridScanCommon,
    signals_to_read_pre_flyscan: list[Readable],
    signals_to_read_during_collection: list[Readable],
    get_xrc_results_from_zocalo: bool = False,
) -> BeamlineSpecificFGSFeatures:
    """Construct the class needed to do beamline-specific parts of the XRC FGS

    Args:
        setup_trigger_plan (Callable): Configure triggering, for example with the Zebra or PandA device.
        Ran directly before kicking off the gridscan.

        tidy_plan (Callable): Tidy up states of devices. Ran at the end of the flyscan, regardless of
        whether or not it finished successfully.

        set_flyscan_params_plan (Callable): Set PV's for the relevant Fast Grid Scan dodal device

        fgs_motors (Callable): Composite device representing the fast grid scan's motion program parameters.

        signals_to_read_pre_flyscan (Callable): Signals which will be read and saved as a bluesky event document
        after all configuration, but before the gridscan.

        signals_to_read_during_collection (Callable): Signals which will be read and saved as a bluesky event
        document whilst the gridscan motion is in progress

        get_xrc_results_from_zocalo (bool): If true, fetch grid scan results from zocalo after completion, as well as
        update the ispyb comment field with information about the results. See _fetch_xrc_results_from_zocalo
    """
    read_pre_flyscan_plan = partial(
        read_hardware_plan,
        signals_to_read_pre_flyscan,
        DocDescriptorNames.HARDWARE_READ_PRE,
    )

    read_during_collection_plan = partial(
        read_hardware_plan,
        signals_to_read_during_collection,
        DocDescriptorNames.HARDWARE_READ_DURING,
    )

    return BeamlineSpecificFGSFeatures(
        setup_trigger_plan,
        tidy_plan,
        set_flyscan_params_plan,
        fgs_motors,
        read_pre_flyscan_plan,
        read_during_collection_plan,
        get_xrc_results_from_zocalo,
    )


def common_flyscan_xray_centre(
    composite: FlyScanEssentialDevices,
    parameters: SpecifiedThreeDGridScan,
    beamline_specific: BeamlineSpecificFGSFeatures,
) -> MsgGenerator:
    """Main entry point of the MX-Bluesky x-ray centering flyscan

    Args:
        composite (FlyScanEssentialDevices): Devices required to perform this plan.

        parameters (SpecifiedThreeDGridScan): Parameters required to perform this plan.

        beamline_specific (BeamlineSpecificFGSFeatures): Configure the beamline-specific version
        of this plan: For example triggering setup and tidy up plans, as well as what to do with the
        centering results.

    With a minimum set of devices and parameters, prepares for; performs; and tidies up a flyscan
    x-ray-center plan. This includes: Configuring desired triggering; writing nexus files; triggering zocalo;
    reading hardware before and during the scan; and tidying up devices after
    the plan is complete. Optionally fetch results from zocalo after completing the grid scan.

    This plan will also push data to ispyb when used with the ispyb_activation_decorator.

    There are a few other useful decorators to use with this plan, see: verify_undulator_gap_before_run_decorator, transmission_and_xbpm_feedback_for_collection_decorator
    """

    def _decorated_flyscan():
        @bpp.set_run_key_decorator(PlanNameConstants.GRIDSCAN_OUTER)
        @bpp.run_decorator(  # attach experiment metadata to the start document
            md={
                "subplan_name": PlanNameConstants.GRIDSCAN_OUTER,
                "mx_bluesky_parameters": parameters.model_dump_json(),
                "activate_callbacks": [
                    "GridscanNexusFileCallback",
                ],
            }
        )
        @bpp.finalize_decorator(lambda: beamline_specific.tidy_plan(composite))
        def run_gridscan_and_tidy(
            fgs_composite: FlyScanEssentialDevices,
            params: SpecifiedThreeDGridScan,
            beamline_specific: BeamlineSpecificFGSFeatures,
        ) -> MsgGenerator:
            yield from beamline_specific.setup_trigger_plan(fgs_composite, parameters)

            LOGGER.info("Starting grid scan")
            yield from bps.stage(
                fgs_composite.zocalo, group=ZOCALO_STAGE_GROUP
            )  # connect to zocalo and make sure the queue is clear
            yield from run_gridscan(fgs_composite, params, beamline_specific)

            LOGGER.info("Grid scan finished")

            if beamline_specific.get_xrc_results_from_zocalo:
                yield from _fetch_xrc_results_from_zocalo(composite.zocalo, parameters)

        yield from run_gridscan_and_tidy(composite, parameters, beamline_specific)

    composite.eiger.set_detector_parameters(parameters.detector_params)
    yield from _decorated_flyscan()


def _fetch_xrc_results_from_zocalo(
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


@bpp.set_run_key_decorator(PlanNameConstants.GRIDSCAN_MAIN)
@bpp.run_decorator(md={"subplan_name": PlanNameConstants.GRIDSCAN_MAIN})
def run_gridscan(
    fgs_composite: FlyScanEssentialDevices,
    parameters: SpecifiedThreeDGridScan,
    beamline_specific: BeamlineSpecificFGSFeatures,
):
    # Currently gridscan only works for omega 0, see https://github.com/DiamondLightSource/mx-bluesky/issues/410
    with TRACER.start_span("moving_omega_to_0"):
        yield from bps.abs_set(fgs_composite.smargon.omega, 0)

    with TRACER.start_span("ispyb_hardware_readings"):
        yield from beamline_specific.read_pre_flyscan_plan()

    LOGGER.info("Setting fgs params")
    yield from beamline_specific.set_flyscan_params_plan()

    LOGGER.info("Waiting for gridscan validity check")
    yield from wait_for_gridscan_valid(beamline_specific.fgs_motors)

    LOGGER.info("Waiting for arming to finish")
    yield from bps.wait(PlanGroupCheckpointConstants.GRID_READY_FOR_DC)
    yield from bps.stage(fgs_composite.eiger)  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809

    yield from kickoff_and_complete_gridscan(
        beamline_specific.fgs_motors,
        fgs_composite.eiger,
        fgs_composite.synchrotron,
        [parameters.scan_points_first_grid, parameters.scan_points_second_grid],
        parameters.scan_indices,
        plan_during_collection=beamline_specific.read_during_collection_plan,
    )
    yield from bps.abs_set(beamline_specific.fgs_motors.z_steps, 0, wait=False)


def wait_for_gridscan_valid(fgs_motors: FastGridScanCommon, timeout=0.5):
    LOGGER.info("Waiting for valid fgs_params")
    SLEEP_PER_CHECK = 0.1
    times_to_check = int(timeout / SLEEP_PER_CHECK)
    for _ in range(times_to_check):
        scan_invalid = yield from bps.rd(fgs_motors.scan_invalid)
        pos_counter = yield from bps.rd(fgs_motors.position_counter)
        LOGGER.debug(
            f"Scan invalid: {scan_invalid} and position counter: {pos_counter}"
        )
        if not scan_invalid and pos_counter == 0:
            LOGGER.info("Gridscan scan valid and position counter reset")
            return
        yield from bps.sleep(SLEEP_PER_CHECK)
    raise SampleException("Scan invalid - pin too long/short/bent and out of range")


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
