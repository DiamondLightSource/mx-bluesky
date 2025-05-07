from __future__ import annotations

from pathlib import Path

from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp
from bluesky.preprocessors import subs_decorator
from bluesky.utils import MsgGenerator
from dodal.devices.backlight import BacklightPosition
from dodal.devices.eiger import EigerDetector
from dodal.devices.oav.oav_parameters import OAVParameters

from mx_bluesky.common.device_setup_plans.manipulate_sample import (
    move_aperture_if_required,
)
from mx_bluesky.common.device_setup_plans.utils import (
    start_preparing_data_collection_then_do_plan,
)
from mx_bluesky.common.experiment_plans.change_aperture_then_move_plan import (
    change_aperture_then_move_to_xtal,
)
from mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan import (
    BeamlineSpecificFGSFeatures,
    common_flyscan_xray_centre,
)
from mx_bluesky.common.experiment_plans.oav_grid_detection_plan import (
    OavGridDetectionComposite,
    grid_detection_plan,
)
from mx_bluesky.common.external_interaction.callbacks.common.grid_detection_callback import (
    GridDetectionCallback,
)
from mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback import (
    ispyb_activation_wrapper,
)
from mx_bluesky.common.parameters.constants import (
    OavConstants,
    PlanGroupCheckpointConstants,
)
from mx_bluesky.common.parameters.device_composites import (
    FlyScanEssentialDevices,
    GridDetectThenXRayCentreComposite,
)
from mx_bluesky.common.parameters.gridscan import GridCommon, SpecifiedThreeDGridScan
from mx_bluesky.common.xrc_result import XRayCentreEventHandler


def grid_detect_then_xray_centre(
    composite: GridDetectThenXRayCentreComposite,
    parameters: GridCommon,
    xrc_composite: FlyScanEssentialDevices,
    xrc_params: SpecifiedThreeDGridScan,
    beamline_specific: BeamlineSpecificFGSFeatures,
    oav_config: str = OavConstants.OAV_CONFIG_JSON,
) -> MsgGenerator:
    """
    A plan which combines the collection of snapshots from the OAV and the determination
    of the grid dimensions to use for the following grid scan.
    """

    eiger: EigerDetector = composite.eiger

    eiger.set_detector_parameters(parameters.detector_params)

    oav_params = OAVParameters("xrayCentring", oav_config)

    flyscan_event_handler = XRayCentreEventHandler()

    @subs_decorator(flyscan_event_handler)
    def plan_to_perform():
        yield from ispyb_activation_wrapper(
            detect_grid_and_do_gridscan(
                composite,
                parameters,
                oav_params,
                xrc_composite,
                xrc_params,
                beamline_specific,
            ),
            parameters,
        )

    yield from start_preparing_data_collection_then_do_plan(
        composite.beamstop,
        eiger,
        composite.detector_motion,
        parameters.detector_params.detector_distance,
        plan_to_perform(),
        group=PlanGroupCheckpointConstants.GRID_READY_FOR_DC,
    )

    assert flyscan_event_handler.xray_centre_results, (
        "Flyscan result event not received or no crystal found and exception not raised"
    )

    yield from change_aperture_then_move_to_xtal(
        flyscan_event_handler.xray_centre_results[0],
        composite.smargon,
        composite.aperture_scatterguard,
    )


def detect_grid_and_do_gridscan(
    composite: GridDetectThenXRayCentreComposite,
    parameters: GridCommon,
    oav_params: OAVParameters,
    xrc_composite: FlyScanEssentialDevices,
    xrc_params: SpecifiedThreeDGridScan,
    beamline_specific: BeamlineSpecificFGSFeatures,
):
    snapshot_template = f"{parameters.detector_params.prefix}_{parameters.detector_params.run_number}_{{angle}}"

    grid_params_callback = GridDetectionCallback()

    @bpp.subs_decorator([grid_params_callback])
    def run_grid_detection_plan(
        oav_params,
        snapshot_template,
        snapshot_dir: Path,
    ):
        grid_detect_composite = OavGridDetectionComposite(
            backlight=composite.backlight,
            oav=composite.oav,
            smargon=composite.smargon,
            pin_tip_detection=composite.pin_tip_detection,
        )

        yield from grid_detection_plan(
            grid_detect_composite,
            oav_params,
            snapshot_template,
            str(snapshot_dir),
            parameters.grid_width_um,
            parameters.box_size_um,
        )

    if parameters.selected_aperture:
        # Start moving the aperture/scatterguard into position without moving it in
        yield from bps.prepare(
            composite.aperture_scatterguard,
            parameters.selected_aperture,
            group=PlanGroupCheckpointConstants.GRID_READY_FOR_DC,
        )

    yield from run_grid_detection_plan(
        oav_params,
        snapshot_template,
        parameters.snapshot_directory,
    )

    yield from bps.abs_set(
        composite.backlight,
        BacklightPosition.OUT,
        group=PlanGroupCheckpointConstants.GRID_READY_FOR_DC,
    )

    yield from move_aperture_if_required(
        composite.aperture_scatterguard,
        parameters.selected_aperture,
        group=PlanGroupCheckpointConstants.GRID_READY_FOR_DC,
    )
    # xrc_composite = FlyScanEssentialDevices(
    #     eiger=composite.eiger,
    #     synchrotron=composite.synchrotron,
    #     zocalo=composite.zocalo,
    #     smargon=composite.smargon,
    # )

    yield from common_flyscan_xray_centre(xrc_composite, xrc_params, beamline_specific)
