from __future__ import annotations

import dataclasses
from collections.abc import Callable
from functools import partial

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
from bluesky.protocols import Readable
from bluesky.utils import FailedStatus, MsgGenerator
from dodal.devices.fast_grid_scan import (
    FastGridScanCommon,
    FastGridScanThreeD,
    GridScanInvalidError,
)

from mx_bluesky.common.experiment_plans.inner_plans.do_fgs import (
    kickoff_and_complete_gridscan,
)
from mx_bluesky.common.experiment_plans.inner_plans.read_hardware import (
    read_hardware_plan,
)
from mx_bluesky.common.parameters.constants import (
    DocDescriptorNames,
    PlanGroupCheckpointConstants,
    PlanNameConstants,
)
from mx_bluesky.common.parameters.device_composites import FlyScanEssentialDevices
from mx_bluesky.common.parameters.gridscan import SpecifiedThreeDGridScan
from mx_bluesky.common.utils.exceptions import (
    SampleError,
)
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.common.utils.tracing import TRACER


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


def generic_tidy(xrc_composite: FlyScanEssentialDevices, wait=True) -> MsgGenerator:
    """Turn off Eiger dev/shm. Ran after the beamline-specific tidy plan"""

    group = "generic_tidy"

    # Turn off dev/shm streaming to avoid filling disk, see https://github.com/DiamondLightSource/hyperion/issues/1395
    LOGGER.info("Turning off Eiger dev/shm streaming")
    # Fix types in ophyd-async (https://github.com/DiamondLightSource/mx-bluesky/issues/855)
    yield from bps.abs_set(
        xrc_composite.eiger.odin.fan.dev_shm_enable,  # type: ignore
        0,
        group=group,
    )
    yield from bps.wait(group)


def construct_beamline_specific_fast_gridscan_features(
    setup_trigger_plan: Callable[..., MsgGenerator],
    tidy_plan: Callable[..., MsgGenerator],
    set_flyscan_params_plan: Callable[..., MsgGenerator],
    fgs_motors: FastGridScanCommon,
    signals_to_read_pre_flyscan: list[Readable],
    signals_to_read_during_collection: list[Readable],
) -> BeamlineSpecificFGSFeatures:
    """Construct the class needed to do beamline-specific parts of the XRC FGS

    Args:
        setup_trigger_plan (Callable): Configure triggering, for example with the Zebra or PandA device.
        Ran directly before kicking off the gridscan.

        tidy_plan (Callable): Tidy up states of devices. Ran at the end of the flyscan, regardless of
        whether or not it finished successfully. Eiger is cleaned up separately

        set_flyscan_params_plan (Callable): Set PV's for the relevant Fast Grid Scan dodal device

        fgs_motors (Callable): Composite device representing the fast grid scan's motion program parameters.

        signals_to_read_pre_flyscan (Callable): Signals which will be read and saved as a bluesky event document
        after all configuration, but before the gridscan.

        signals_to_read_during_collection (Callable): Signals which will be read and saved as a bluesky event
        document whilst the gridscan motion is in progress
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
    x-ray-center plan. This includes: Configuring desired triggering; writing nexus files;
    reading hardware before and during the scan; and tidying up devices after
    the plan is complete. Results can be fetched via zocalo by using the use_gridscan_with_zocalo_decorator
    preprocessor.

    This plan will also push data to ispyb when used with the ispyb_activation_decorator.

    There are a few other useful decorators to use with this plan, see: verify_undulator_gap_before_run_decorator, transmission_and_xbpm_feedback_for_collection_decorator
    """

    def _overall_tidy():
        yield from beamline_specific.tidy_plan()
        yield from generic_tidy(composite)

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
        @bpp.finalize_decorator(lambda: _overall_tidy())
        def run_gridscan_and_tidy(
            fgs_composite: FlyScanEssentialDevices,
            params: SpecifiedThreeDGridScan,
            beamline_specific: BeamlineSpecificFGSFeatures,
        ) -> MsgGenerator:
            yield from beamline_specific.setup_trigger_plan(fgs_composite, parameters)

            LOGGER.info("Starting grid scan")
            yield from run_gridscan(fgs_composite, params, beamline_specific)

            LOGGER.info("Grid scan finished")

        yield from run_gridscan_and_tidy(composite, parameters, beamline_specific)

    composite.eiger.set_detector_parameters(parameters.detector_params)
    yield from _decorated_flyscan()


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

    try:
        yield from beamline_specific.set_flyscan_params_plan()
    except FailedStatus as e:
        if isinstance(e.__cause__, GridScanInvalidError):
            raise SampleError(
                "Scan invalid - gridscan not valid for detected pin position"
            ) from e
        else:
            raise e

    LOGGER.info("Waiting for arming to finish")
    yield from bps.wait(PlanGroupCheckpointConstants.GRID_READY_FOR_DC)
    yield from bps.stage(fgs_composite.eiger, wait=True)

    yield from kickoff_and_complete_gridscan(
        beamline_specific.fgs_motors,
        fgs_composite.eiger,
        fgs_composite.synchrotron,
        [parameters.scan_points_first_grid, parameters.scan_points_second_grid],
        plan_during_collection=beamline_specific.read_during_collection_plan,
    )

    # GDA's 3D gridscans requires Z steps to be at 0, so make sure we leave this device
    # in a GDA-happy state.
    if isinstance(beamline_specific.fgs_motors, FastGridScanThreeD):
        yield from bps.abs_set(beamline_specific.fgs_motors.z_steps, 0, wait=False)
