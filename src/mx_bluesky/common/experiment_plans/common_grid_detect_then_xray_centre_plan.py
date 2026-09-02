from __future__ import annotations

from pathlib import Path
from typing import Protocol, TypeVar

from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp
from bluesky.utils import MsgGenerator
from dodal.common.beamlines.beamline_utils import get_config_client
from dodal.devices.backlight import InOut
from dodal.devices.detector import DetectorParams, TriggerMode
from dodal.devices.eiger import EigerDetector
from dodal.devices.oav.oav_parameters import OAVParameters

from mx_bluesky.common.device_setup_plans.manipulate_sample import (
    move_aperture_if_required,
)
from mx_bluesky.common.device_setup_plans.utils import (
    start_preparing_data_collection_then_do_plan,
)
from mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan import (
    BeamlineSpecificFGSFeatures,
    TParameters,
    common_flyscan_xray_centre,
)
from mx_bluesky.common.experiment_plans.oav_grid_detection_plan import (
    OavGridDetectionComposite,
    grid_detection_plan,
)
from mx_bluesky.common.experiment_plans.oav_snapshot_plan import (
    setup_beamline_for_oav,
)
from mx_bluesky.common.external_interaction.callbacks.common.grid_detection_callback import (
    GridDetectionCallback,
    GridParamUpdate,
)
from mx_bluesky.common.external_interaction.callbacks.grid.grid_detect_and_scan.ispyb_callback import (
    ispyb_activation_decorator,
)
from mx_bluesky.common.parameters.constants import (
    OavConstants,
    PlanGroupCheckpointConstants,
)
from mx_bluesky.common.parameters.device_composites import (
    GridDetectAndGridScanEssentialDevices,
)
from mx_bluesky.common.parameters.gridscan import (
    GridDetectionParams,
    GridScanParams,
)
from mx_bluesky.common.utils.log import LOGGER

TGridDetectAndGridScanEssentialDevices = TypeVar(
    "TGridDetectAndGridScanEssentialDevices",
    bound=GridDetectAndGridScanEssentialDevices,
)


def grid_detect_then_xray_centre(
    composite: TGridDetectAndGridScanEssentialDevices,
    parameters: TParameters,
    grid_detection_params: GridDetectionParams,
    detector_params: DetectorParams,
    construct_beamline_specific: ConstructBeamlineSpecificFeatures[
        TGridDetectAndGridScanEssentialDevices, TParameters
    ],
    oav_config: str = OavConstants.OAV_CONFIG_JSON,
) -> MsgGenerator[GridScanParams]:
    """
    Perform grid detection and a gridscan.
    This is a wrapper for detect_grid_and_do_gridscan which activates callbacks for ispyb.
    Plans that do pin tip detection should call detect_grid_and_do_gridscan directly as
    callbacks will already have been registered earlier.

    Args:
        composite (TGridDetectAndGridScanEssentialDevices): Devices needed for this plan.
        parameters (TParameters): The top-level experiment parameters.
        grid_detection_params (GridDetectionParams): The base parameters used to define the detected grids.
        detector_params (DetectorParams): Detector parameters.
        construct_beamline_specific: Factory method that provides experiment plans for the beamline specific
            customisation points.
        oav_config (str): Optional path to the OAV configuration
    Returns:
        GridScanParams: The detected grid parameters.
    """

    eiger: EigerDetector = composite.eiger

    oav_params = OAVParameters(get_config_client(), "xrayCentring", oav_config)

    grid_scan_params = None

    @ispyb_activation_decorator(parameters, detector_params)
    def plan_to_perform():
        nonlocal grid_scan_params
        grid_scan_params = yield from detect_grid_and_do_gridscan(
            composite,
            parameters,
            grid_detection_params,
            oav_params,
            detector_params,
            construct_beamline_specific,
        )

    assert parameters.trigger_mode != TriggerMode.SET_FRAMES, (
        "Cannot pre-arm detector before grid detection when trigger mode is SET_FRAMES"
    )
    eiger.set_detector_parameters(detector_params)

    yield from start_preparing_data_collection_then_do_plan(
        composite.beamstop,
        eiger,
        composite.detector_motion,
        detector_params.detector_distance,
        plan_to_perform(),
        group=PlanGroupCheckpointConstants.GRID_READY_FOR_DC,
    )

    assert grid_scan_params
    return grid_scan_params


def detect_grid_and_do_gridscan(
    composite: TGridDetectAndGridScanEssentialDevices,
    parameters: TParameters,
    grid_detection_params: GridDetectionParams,
    oav_params: OAVParameters,
    detector_params: DetectorParams,
    construct_beamline_specific: ConstructBeamlineSpecificFeatures[
        TGridDetectAndGridScanEssentialDevices, TParameters
    ],
) -> MsgGenerator[GridScanParams]:
    """
    Main experiment plan for grid detection and gridscan.

    Args:
        composite (TGridDetectAndGridScanEssentialDevices): Devices needed for this plan.
        parameters (TParameters): The top-level experiment parameters.
        grid_detection_params (GridDetectionParams): The base parameters used to define the detected grids.
        oav_params (OAVParameters): Parameters for the OAV
        detector_params (DetectorParams): Detector parameters.
        construct_beamline_specific: Factory method that provides experiment plans for the beamline specific
            customisation points.
    Returns:
        GridScanParams: The detected grid parameters.
    """
    grid_detect_params = GridDetectionParams(
        box_size_um=grid_detection_params.box_size_um,
        grid_width_um=grid_detection_params.grid_width_um,
    )
    snapshot_template = f"{parameters.file_name}_{detector_params.run_number}_{{angle}}"

    grid_params_callback = GridDetectionCallback()

    yield from setup_beamline_for_oav(
        composite.gonio,
        composite.backlight,
        composite.aperture_scatterguard,
        wait=True,
    )

    if parameters.selected_aperture:
        # Start moving the aperture/scatterguard into position without moving it in
        yield from bps.prepare(
            composite.aperture_scatterguard,
            parameters.selected_aperture,
            group=PlanGroupCheckpointConstants.PREPARE_APERTURE,
        )

    yield from bpp.subs_wrapper(
        _run_grid_detection_plan(
            composite,
            grid_detect_params,
            oav_params,
            snapshot_template,
            parameters.snapshot_directory,
        ),
        grid_params_callback,
    )

    yield from bps.abs_set(
        composite.backlight,
        InOut.OUT,
        group=PlanGroupCheckpointConstants.GRID_READY_FOR_DC,
    )

    yield from bps.wait(PlanGroupCheckpointConstants.PREPARE_APERTURE)
    yield from move_aperture_if_required(
        composite.aperture_scatterguard,
        parameters.selected_aperture,
        group=PlanGroupCheckpointConstants.GRID_READY_FOR_DC,
    )
    grid_scan_params = create_parameters_for_flyscan_xray_centre(
        grid_params_callback.get_grid_parameters()
    )
    beamline_specific = construct_beamline_specific(
        composite, parameters, grid_scan_params
    )

    yield from common_flyscan_xray_centre(
        composite, parameters, detector_params, grid_scan_params, beamline_specific
    )

    return grid_scan_params


def _run_grid_detection_plan(
    grid_detect_composite: OavGridDetectionComposite,
    grid_detect_params: GridDetectionParams,
    oav_params: OAVParameters,
    snapshot_template: str,
    snapshot_dir: Path,
):
    yield from grid_detection_plan(
        grid_detect_composite,
        oav_params,
        snapshot_template,
        str(snapshot_dir),
        grid_detect_params.grid_width_um,
        grid_detect_params.box_size_um,
    )


class ConstructBeamlineSpecificFeatures(
    Protocol[TGridDetectAndGridScanEssentialDevices, TParameters]
):
    def __call__(
        self,
        xrc_composite: TGridDetectAndGridScanEssentialDevices,
        xrc_parameters: TParameters,
        grid_scan_params: GridScanParams,
    ) -> BeamlineSpecificFGSFeatures[
        TGridDetectAndGridScanEssentialDevices, TParameters
    ]: ...


def create_parameters_for_flyscan_xray_centre(
    grid_parameters: GridParamUpdate,
) -> GridScanParams:
    grid_scan_params = GridScanParams(
        omega_starts_deg=[0, 90],
        x_start_um=grid_parameters["x_start_um"],
        y_starts_um=grid_parameters["y_starts_um"],
        z_starts_um=grid_parameters["z_starts_um"],
        x_steps=grid_parameters["x_steps"],
        y_steps=grid_parameters["y_steps"],
        x_step_size_um=grid_parameters["x_step_size_um"],
        y_step_sizes_um=grid_parameters["y_step_sizes_um"],
    )
    LOGGER.info(f"Parameters for FGS: {grid_scan_params}")
    return grid_scan_params
