from __future__ import annotations

import dataclasses
from collections.abc import Callable, Sequence
from functools import partial
from typing import Any, Generic, TypeVar

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
from bluesky.protocols import Readable
from bluesky.utils import FailedStatus, MsgGenerator
from dodal.devices.detector import DetectorParams
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
from mx_bluesky.common.parameters.components import (
    DiffractionExperiment,
    DiffractionExperimentWithSample,
)
from mx_bluesky.common.parameters.constants import (
    DocDescriptorNames,
    PlanGroupCheckpointConstants,
    PlanNameConstants,
)
from mx_bluesky.common.parameters.device_composites import (
    FlyScanEssentialDevices,
)
from mx_bluesky.common.parameters.gridscan import (
    GridScanParams,
)
from mx_bluesky.common.utils.exceptions import (
    SampleError,
)
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.common.utils.tracing import TRACER

TSetupParameters = TypeVar(
    "TSetupParameters", bound=DiffractionExperiment, contravariant=True
)
TParameters = TypeVar("TParameters", bound=DiffractionExperimentWithSample)
# TFlyScanDevices: TypeAlias = FlyScanEssentialDevices[TGonioWithOmega, TDetector]
TFlyScanDevices = TypeVar("TFlyScanDevices", bound=FlyScanEssentialDevices)


@dataclasses.dataclass
class BeamlineSpecificDetectorFeatures(Generic[TFlyScanDevices]):
    """Defines plans specific to arming and disarming the detector.
    Attributes:
        pre_arm_detector_plan: A plan that may be called early on to start arming the detector.
            Supplied with a group name that will be waited on to ensure pre-arming completes.
        arm_detector_plan: A plan that is called later to fully arm the detector. Supplied with a group name
            that will be waited on to ensure arming completes.
        disarm_detector_plan: A plan that will be called to complete the acquisition.
        tidy_detector_plan: The detector-specific plan for cleaning up the detector.
        detector_zocalo_hw_read_signals: The list of signals to read when generating the ZOCALO_HW_READ event.
        detector_hw_read_during_signals: The list of signals to read when generating the HARDWARE_READ_DURING event.
    """

    pre_arm_detector_plan: Callable[[TFlyScanDevices, DetectorParams, str], MsgGenerator]
    arm_detector_plan: Callable[[TFlyScanDevices, DetectorParams, str], MsgGenerator]
    disarm_detector_plan: Callable[[TFlyScanDevices], MsgGenerator]
    tidy_detector_plan: Callable[[TFlyScanDevices], MsgGenerator]
    detector_zocalo_hw_read_signals: Sequence
    detector_hw_read_during_signals: Sequence


@dataclasses.dataclass
class BeamlineSpecificFGSFeatures(
    BeamlineSpecificDetectorFeatures, Generic[TFlyScanDevices, TSetupParameters]
):
    setup_trigger_plan: Callable[
        [TFlyScanDevices, TSetupParameters, GridScanParams], MsgGenerator
    ]
    tidy_plan: Callable[..., MsgGenerator]
    set_flyscan_params_plan: Callable[[GridScanParams], MsgGenerator]
    fgs_motors: FastGridScanCommon
    read_pre_flyscan_plan: Callable[
        ..., MsgGenerator
    ]  # Eventually replace with https://github.com/DiamondLightSource/mx-bluesky/issues/819
    read_during_collection_plan: Callable[..., MsgGenerator]


def construct_beamline_specific_fast_gridscan_features(
    detector_features: BeamlineSpecificDetectorFeatures[TFlyScanDevices],
    setup_trigger_plan: Callable[
        [TFlyScanDevices, TSetupParameters, GridScanParams], MsgGenerator
    ],
    tidy_plan: Callable[..., MsgGenerator],
    set_flyscan_params_plan: Callable[[GridScanParams], MsgGenerator],
    fgs_motors: FastGridScanCommon,
    signals_to_read_pre_flyscan: Sequence[Readable],
    signals_to_read_during_collection: Sequence[Readable],
) -> BeamlineSpecificFGSFeatures[TFlyScanDevices, TSetupParameters]:
    """Construct the class needed to do beamline-specific parts of the XRC FGS

    Args:
        detector_features: The features specific to setting up the detector
        setup_trigger_plan (Callable): Configure triggering, for example with the Zebra or PandA device.
        Ran directly before kicking off the gridscan.

        tidy_plan (Callable): Tidy up states of devices. Ran at the end of the flyscan, regardless of
        whether or not it finished successfully. Zocalo and Eiger are cleaned up separately

        set_flyscan_params_plan (Callable): Set PV's for the relevant Fast Grid Scan dodal device

        fgs_motors (Callable): Composite device representing the fast grid scan's motion program parameters.

        signals_to_read_pre_flyscan (Callable): Signals which will be read and saved as a bluesky event document
        after all configuration, but before the gridscan.

        signals_to_read_during_collection (Callable): Signals which will be read and saved as a bluesky event
        document whilst the gridscan motion is in progress

        detector_signals_to_read: The list of detector signals to read when generating callback events
    """
    read_pre_flyscan_plan = partial(
        read_hardware_plan,
        signals_to_read_pre_flyscan,
        DocDescriptorNames.HARDWARE_READ_PRE,
    )

    read_during_collection_plan = partial(
        read_hardware_plan,
        [*signals_to_read_during_collection, *detector_features.detector_hw_read_during_signals],
        DocDescriptorNames.HARDWARE_READ_DURING,
    )

    return BeamlineSpecificFGSFeatures(
        pre_arm_detector_plan=detector_features.pre_arm_detector_plan,
        arm_detector_plan=detector_features.arm_detector_plan,
        disarm_detector_plan=detector_features.disarm_detector_plan,
        tidy_detector_plan=detector_features.tidy_detector_plan,
        detector_zocalo_hw_read_signals=detector_features.detector_zocalo_hw_read_signals,
        detector_hw_read_during_signals=detector_features.detector_hw_read_during_signals,
        setup_trigger_plan=setup_trigger_plan,
        tidy_plan=tidy_plan,
        set_flyscan_params_plan=set_flyscan_params_plan,
        fgs_motors=fgs_motors,
        read_pre_flyscan_plan=read_pre_flyscan_plan,
        read_during_collection_plan=read_during_collection_plan,
    )


def common_flyscan_xray_centre(
    composite: TFlyScanDevices,
    parameters: TParameters,
    xrc_detector_params: DetectorParams,
    grid_scan_parameters: GridScanParams,
    beamline_specific: BeamlineSpecificFGSFeatures[TFlyScanDevices, TParameters],
) -> MsgGenerator:
    """Main entry point of the MX-Bluesky x-ray centering flyscan

    Args:
        composite (FlyScanEssentialDevices): Devices required to perform this plan.

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
        yield from beamline_specific.tidy_plan()
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
            fgs_composite: TFlyScanDevices,
        ) -> MsgGenerator:
            yield from beamline_specific.setup_trigger_plan(
                fgs_composite, parameters, grid_scan_parameters
            )

            LOGGER.info("Starting grid scan")
            yield from run_gridscan(
                fgs_composite, grid_scan_parameters, xrc_detector_params, beamline_specific
            )

            LOGGER.info("Grid scan finished")

        yield from run_gridscan_and_tidy(composite)

    composite.detector.set_detector_parameters(xrc_detector_params)
    yield from _decorated_flyscan()


def run_gridscan(
    fgs_composite: TFlyScanDevices,
    grid_scan_params: GridScanParams,
    detector_params: DetectorParams,
    beamline_specific: BeamlineSpecificFGSFeatures[TFlyScanDevices, Any],
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

    yield from beamline_specific.arm_detector_plan(fgs_composite,
                                                   detector_params,
                                                   PlanGroupCheckpointConstants.GRIDSCAN_ARMING_COMPLETE)
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
