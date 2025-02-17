from __future__ import annotations

import dataclasses
from collections.abc import Callable, Sequence
from functools import partial
from typing import Generic, TypeVar

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
import numpy as np
import pydantic
from blueapi.core import BlueskyContext
from bluesky.protocols import Readable
from bluesky.utils import MsgGenerator
from dodal.devices.attenuator.attenuator import (
    ReadOnlyAttenuator,
)
from dodal.devices.backlight import Backlight
from dodal.devices.dcm import DCM
from dodal.devices.eiger import EigerDetector
from dodal.devices.fast_grid_scan import (
    FastGridScanCommon,
    ZebraFastGridScan,
)
from dodal.devices.smargon import Smargon
from dodal.devices.synchrotron import Synchrotron
from dodal.devices.undulator import Undulator
from dodal.devices.xbpm_feedback import XBPMFeedback
from dodal.devices.zebra.zebra import Zebra
from dodal.devices.zocalo import ZocaloResults
from dodal.devices.zocalo.zocalo_results import (
    ZOCALO_READING_PLAN_NAME,
    ZOCALO_STAGE_GROUP,
    XrcResult,
    get_full_processing_results,
)

from mx_bluesky.common.device_setup_plans.xbpm_feedback import (
    transmission_and_xbpm_feedback_for_collection_decorator,
)
from mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback import (
    ispyb_activation_wrapper,
)
from mx_bluesky.common.parameters.constants import (
    DocDescriptorNames,
    EnvironmentConstants,
    GridscanParamConstants,
    PlanGroupCheckpointConstants,
    PlanNameConstants,
)
from mx_bluesky.common.parameters.gridscan import SpecifiedThreeDGridScan
from mx_bluesky.common.plans.inner_plans.do_fgs import kickoff_and_complete_gridscan
from mx_bluesky.common.plans.read_hardware import (
    read_hardware_plan,
)
from mx_bluesky.common.utils.context import device_composite_from_context
from mx_bluesky.common.utils.exceptions import (
    CrystalNotFoundException,
    SampleException,
)
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.common.utils.tracing import TRACER
from mx_bluesky.common.xrc_result import XRayCentreEventHandler, XRayCentreResult


# Saves needing to write 'assert not None' everywhere
def null_plan(*args):
    yield from bps.null()


T = TypeVar("T", bound=ReadOnlyAttenuator)  # Ensures T is always a subclass of A


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class FlyScanEssentialDevices(Generic[T]):
    attenuator: T
    backlight: Backlight
    eiger: EigerDetector
    zebra_fast_grid_scan: ZebraFastGridScan
    synchrotron: Synchrotron
    xbpm_feedback: XBPMFeedback
    zebra: Zebra
    zocalo: ZocaloResults
    smargon: Smargon
    undulator: Undulator
    dcm: DCM


NullPlanType = Callable[[], MsgGenerator]


@dataclasses.dataclass
class BeamlineSpecificFGSFeatures:
    setup_trigger_plan: Callable[..., MsgGenerator]
    tidy_plan: Callable[..., MsgGenerator]
    set_flyscan_params_plan: Callable[..., MsgGenerator]
    fgs_motors: FastGridScanCommon
    read_pre_flyscan_plan: Callable[..., MsgGenerator]
    read_during_collection_plan: Callable[..., MsgGenerator]
    plan_after_getting_xrc_results: Callable[..., MsgGenerator] = null_plan


def construct_beamline_specific_FGS_features(
    setup_trigger_plan: Callable[..., MsgGenerator],
    tidy_plan: Callable[..., MsgGenerator],
    set_flyscan_params_plan: Callable[..., MsgGenerator],
    fgs_motors: FastGridScanCommon,
    signals_to_read_pre_flyscan: list[Readable],
    signals_to_read_during_collection: list[Readable],
    plan_after_getting_xrc_results=null_plan,
) -> BeamlineSpecificFGSFeatures:
    """Construct the class needed to do beamline-specific parts of the XRC FGS

    Args:
        setup_trigger_plan (Callable): Configure any triggering, for example with the Zebra or PandA device. Ran directly before kicking off the gridscan.

        tidy_plan (Callable): Tidy up states of devices. Ran at the end of the flyscan, regardless of whether or not it finished successfully.

        set_flyscan_params_plan (Callable): Set PV's for the relevant Fast Grid Scan dodal device

        fgs_motors (Callable): Composite device representing the fast grid scan's motion program parameters.

        signals_to_read_pre_flyscan (Callable): Signals which will be read and saved as a bluesky event document after all configuration, but before the gridscan.

        signals_to_read_during_collection (Callable): Signals which will be read and saved as a bluesky event document whilst the gridscan motion is in progress

        plan_after_getting_xrc_results (Callable): Optional plan which is ran after x-ray centring results have been retrieved from Zocalo.
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
        plan_after_getting_xrc_results,
    )


def create_devices(context: BlueskyContext) -> FlyScanEssentialDevices:
    """Creates the devices required for the plan and connect to them"""
    return device_composite_from_context(context, FlyScanEssentialDevices)


def highest_level_flyscan_xray_centre(
    composite: FlyScanEssentialDevices,
    parameters: SpecifiedThreeDGridScan,
    feature_controlled: BeamlineSpecificFGSFeatures,
) -> MsgGenerator:
    """Main entry point of the MX-Bluesky x-ray centering flyscan

    Args:
        composite (FlyScanEssentialDevices): Devices required to perform this plan.

        parameters (SpecifiedThreeDGridScan): Parameters required to perform this plan.

        feature_controlled (BeamlineSpecificFGSFeatures): Configure the beamline-specific version of this plan: For example triggering setup and tidy up plans, as well as what to do with the centering results.



    With a minimum set of devices and parameters, prepares for; performs; and tidies up from a flyscan x-ray-center plan. This includes: Configuring desired triggering; writing nexus files; pushing data to ispyb; triggering zocalo; reading hardware before and during the scan; optionally performing a plan using the results; and tidying up devices after the plan is complete. For more information, see https://diamondlightsource.github.io/mx-bluesky/main/index.html

    """

    xrc_event_handler = XRayCentreEventHandler()

    @bpp.subs_decorator(xrc_event_handler)
    def flyscan_and_fetch_results() -> MsgGenerator:
        yield from ispyb_activation_wrapper(
            flyscan_xray_centre_no_move(composite, parameters, feature_controlled),
            parameters,
        )

    yield from flyscan_and_fetch_results()

    xray_centre_results = xrc_event_handler.xray_centre_results
    assert xray_centre_results, (
        "Flyscan result event not received or no crystal found and exception not raised"
    )

    yield from feature_controlled.plan_after_getting_xrc_results(
        composite, parameters, xray_centre_results[0]
    )


def flyscan_xray_centre_no_move(
    composite: FlyScanEssentialDevices,
    parameters: SpecifiedThreeDGridScan,
    feature_controlled: BeamlineSpecificFGSFeatures,
) -> MsgGenerator:
    """Perform a flyscan and determine the centres of interest"""

    composite.eiger.set_detector_parameters(parameters.detector_params)
    composite.zocalo.zocalo_environment = EnvironmentConstants.ZOCALO_ENV

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
    @bpp.finalize_decorator(lambda: feature_controlled.tidy_plan(composite))
    @transmission_and_xbpm_feedback_for_collection_decorator(
        composite.undulator,
        composite.xbpm_feedback,
        composite.attenuator,
        composite.dcm,
        parameters.transmission_frac,
    )
    def run_gridscan_and_fetch_and_tidy(
        fgs_composite: FlyScanEssentialDevices,
        params: SpecifiedThreeDGridScan,
        feature_controlled: BeamlineSpecificFGSFeatures,
    ) -> MsgGenerator:
        yield from run_gridscan_and_fetch_results(
            fgs_composite, params, feature_controlled
        )

    yield from run_gridscan_and_fetch_and_tidy(
        composite, parameters, feature_controlled
    )


@bpp.set_run_key_decorator(PlanNameConstants.GRIDSCAN_AND_MOVE)
@bpp.run_decorator(md={"subplan_name": PlanNameConstants.GRIDSCAN_AND_MOVE})
def run_gridscan_and_fetch_results(
    fgs_composite: FlyScanEssentialDevices,
    parameters: SpecifiedThreeDGridScan,
    feature_controlled: BeamlineSpecificFGSFeatures,
) -> MsgGenerator:
    """A multi-run plan which runs a gridscan, gets the results from zocalo
    and fires an event with the centres of mass determined by zocalo"""

    yield from feature_controlled.setup_trigger_plan(fgs_composite, parameters)

    LOGGER.info("Starting grid scan")
    yield from bps.stage(
        fgs_composite.zocalo, group=ZOCALO_STAGE_GROUP
    )  # connect to zocalo and make sure the queue is clear
    yield from run_gridscan(fgs_composite, parameters, feature_controlled)

    LOGGER.info("Grid scan finished, getting results.")

    try:
        with TRACER.start_span("wait_for_zocalo"):
            yield from bps.trigger_and_read(
                [fgs_composite.zocalo], name=ZOCALO_READING_PLAN_NAME
            )
            LOGGER.info("Zocalo triggered and read, interpreting results.")
            xrc_results = yield from get_full_processing_results(fgs_composite.zocalo)
            LOGGER.info(f"Got xray centres, top 5: {xrc_results[:5]}")
            filtered_results = [
                result
                for result in xrc_results
                if result["total_count"]
                >= GridscanParamConstants.ZOCALO_MIN_TOTAL_COUNT_THRESHOLD
            ]
            discarded_count = len(xrc_results) - len(filtered_results)
            if discarded_count > 0:
                LOGGER.info(
                    f"Removed {discarded_count} results because below threshold"
                )
            if filtered_results:
                flyscan_results = [
                    _xrc_result_in_boxes_to_result_in_mm(xr, parameters)
                    for xr in filtered_results
                ]
            else:
                LOGGER.warning("No X-ray centre received")
                raise CrystalNotFoundException()
            yield from _fire_xray_centre_result_event(flyscan_results)

    finally:
        # Turn off dev/shm streaming to avoid filling disk, see https://github.com/DiamondLightSource/hyperion/issues/1395
        LOGGER.info("Turning off Eiger dev/shm streaming")
        yield from bps.abs_set(fgs_composite.eiger.odin.fan.dev_shm_enable, 0)  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809

        # Wait on everything before returning to GDA (particularly apertures), can be removed
        # when we do not return to GDA here
        yield from bps.wait()


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


@bpp.set_run_key_decorator(PlanNameConstants.FLYSCAN_RESULTS)
def _fire_xray_centre_result_event(results: Sequence[XRayCentreResult]):
    def empty_plan():
        return iter([])

    yield from bpp.run_wrapper(
        empty_plan(),
        md={"xray_centre_results": [dataclasses.asdict(r) for r in results]},
    )


@bpp.set_run_key_decorator(PlanNameConstants.GRIDSCAN_MAIN)
@bpp.run_decorator(md={"subplan_name": PlanNameConstants.GRIDSCAN_MAIN})
def run_gridscan(
    fgs_composite: FlyScanEssentialDevices,
    parameters: SpecifiedThreeDGridScan,
    feature_controlled: BeamlineSpecificFGSFeatures,
    md={  # noqa
        "plan_name": PlanNameConstants.GRIDSCAN_MAIN,
    },
):
    # Currently gridscan only works for omega 0, see #
    with TRACER.start_span("moving_omega_to_0"):
        yield from bps.abs_set(fgs_composite.smargon.omega, 0)

    # We only subscribe to the communicator callback for run_gridscan, so this is where
    # we should generate an event reading the values which need to be included in the
    # ispyb deposition
    with TRACER.start_span("ispyb_hardware_readings"):
        yield from feature_controlled.read_pre_flyscan_plan()

    LOGGER.info("Setting fgs params")
    yield from feature_controlled.set_flyscan_params_plan()

    LOGGER.info("Waiting for gridscan validity check")
    yield from wait_for_gridscan_valid(feature_controlled.fgs_motors)

    LOGGER.info("Waiting for arming to finish")
    yield from bps.wait(PlanGroupCheckpointConstants.GRID_READY_FOR_DC)
    yield from bps.stage(fgs_composite.eiger)  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809

    yield from kickoff_and_complete_gridscan(
        feature_controlled.fgs_motors,
        fgs_composite.eiger,
        fgs_composite.synchrotron,
        [parameters.scan_points_first_grid, parameters.scan_points_second_grid],
        parameters.scan_indices,
        plan_during_collection=feature_controlled.read_during_collection_plan,
    )
    yield from bps.abs_set(feature_controlled.fgs_motors.z_steps, 0, wait=False)


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
