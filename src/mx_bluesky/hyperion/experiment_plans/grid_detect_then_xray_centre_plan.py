from __future__ import annotations

from pathlib import Path

from blueapi.core import BlueskyContext
from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp
from bluesky.preprocessors import subs_decorator
from bluesky.utils import MsgGenerator
from dodal.devices.backlight import BacklightPosition
from dodal.devices.eiger import EigerDetector
from dodal.devices.oav.oav_parameters import OAVParameters
from dodal.plans.preprocessors.verify_undulator_gap import (
    verify_undulator_gap_before_run_decorator,
)

from mx_bluesky.common.device_setup_plans.manipulate_sample import (
    move_aperture_if_required,
)
from mx_bluesky.common.experiment_plans.change_aperture_then_move_plan import (
    change_aperture_then_move_to_xtal,
)
from mx_bluesky.common.experiment_plans.oav_grid_detection_plan import (
    OavGridDetectionComposite,
    grid_detection_plan,
)
from mx_bluesky.common.external_interaction.callbacks.common.grid_detection_callback import (
    GridDetectionCallback,
    GridParamUpdate,
)
from mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback import (
    ispyb_activation_wrapper,
)
from mx_bluesky.common.parameters.constants import OavConstants
from mx_bluesky.common.parameters.gridscan import GridCommon
from mx_bluesky.common.plans.common_flyscan_xray_centre_plan import (
    BeamlineSpecificFGSFeatures,
    common_flyscan_xray_centre,
)
from mx_bluesky.common.preprocessors.preprocessors import (
    transmission_and_xbpm_feedback_for_collection_decorator,
)
from mx_bluesky.common.utils.context import device_composite_from_context
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.common.xrc_result import XRayCentreEventHandler
from mx_bluesky.hyperion.device_setup_plans.utils import (
    start_preparing_data_collection_then_do_plan,
)
from mx_bluesky.hyperion.experiment_plans.hyperion_flyscan_xray_centre_plan import (
    construct_hyperion_specific_features,
)
from mx_bluesky.hyperion.parameters.constants import CONST
from mx_bluesky.hyperion.parameters.device_composites import (
    GridDetectThenXRayCentreComposite,
    HyperionFlyScanXRayCentreComposite,
)
from mx_bluesky.hyperion.parameters.gridscan import (
    GridScanWithEdgeDetect,
    HyperionSpecifiedThreeDGridScan,
)


def create_devices(context: BlueskyContext) -> GridDetectThenXRayCentreComposite:
    return device_composite_from_context(context, GridDetectThenXRayCentreComposite)


def create_parameters_for_flyscan_xray_centre(
    grid_scan_with_edge_params: GridCommon,
    grid_parameters: GridParamUpdate,
) -> HyperionSpecifiedThreeDGridScan:
    params_json = grid_scan_with_edge_params.model_dump()
    params_json.update(grid_parameters)
    flyscan_xray_centre_parameters = HyperionSpecifiedThreeDGridScan(**params_json)
    LOGGER.info(f"Parameters for FGS: {flyscan_xray_centre_parameters}")
    return flyscan_xray_centre_parameters


def detect_grid_and_do_gridscan(
    composite: GridDetectThenXRayCentreComposite,
    parameters: GridCommon,
    oav_params: OAVParameters,
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
            group=CONST.WAIT.PREPARE_APERTURE,
        )

    yield from run_grid_detection_plan(
        oav_params,
        snapshot_template,
        parameters.snapshot_directory,
    )

    yield from bps.abs_set(
        composite.backlight, BacklightPosition.OUT, group=CONST.WAIT.GRID_READY_FOR_DC
    )

    yield from bps.wait(CONST.WAIT.PREPARE_APERTURE)
    yield from move_aperture_if_required(
        composite.aperture_scatterguard,
        parameters.selected_aperture,
        group=CONST.WAIT.GRID_READY_FOR_DC,
    )

    xrc_composite = HyperionFlyScanXRayCentreComposite(
        aperture_scatterguard=composite.aperture_scatterguard,
        attenuator=composite.attenuator,
        backlight=composite.backlight,
        eiger=composite.eiger,
        panda_fast_grid_scan=composite.panda_fast_grid_scan,
        flux=composite.flux,
        s4_slit_gaps=composite.s4_slit_gaps,
        smargon=composite.smargon,
        undulator=composite.undulator,
        synchrotron=composite.synchrotron,
        xbpm_feedback=composite.xbpm_feedback,
        zebra=composite.zebra,
        zocalo=composite.zocalo,
        panda=composite.panda,
        zebra_fast_grid_scan=composite.zebra_fast_grid_scan,
        dcm=composite.dcm,
        robot=composite.robot,
        sample_shutter=composite.sample_shutter,
    )

    params = create_parameters_for_flyscan_xray_centre(
        parameters, grid_params_callback.get_grid_parameters()
    )

    beamline_specific = construct_hyperion_specific_features(xrc_composite, params)

    yield from _gridscan_with_undulator_checks(xrc_composite, params, beamline_specific)


def _gridscan_with_undulator_checks(
    composite: HyperionFlyScanXRayCentreComposite,
    params: HyperionSpecifiedThreeDGridScan,
    beamline_specific: BeamlineSpecificFGSFeatures,
):
    @transmission_and_xbpm_feedback_for_collection_decorator(
        composite, params.transmission_frac
    )
    @verify_undulator_gap_before_run_decorator(composite)
    def _inner():
        yield from common_flyscan_xray_centre(composite, params, beamline_specific)

    yield from _inner()


def grid_detect_then_xray_centre(
    composite: GridDetectThenXRayCentreComposite,
    parameters: GridScanWithEdgeDetect,
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
            ),
            parameters,
        )

    yield from start_preparing_data_collection_then_do_plan(
        composite.beamstop,
        eiger,
        composite.detector_motion,
        parameters.detector_params.detector_distance,
        plan_to_perform(),
        group=CONST.WAIT.GRID_READY_FOR_DC,
    )

    assert flyscan_event_handler.xray_centre_results, (
        "Flyscan result event not received or no crystal found and exception not raised"
    )

    yield from change_aperture_then_move_to_xtal(
        flyscan_event_handler.xray_centre_results[0],
        composite.smargon,
        composite.aperture_scatterguard,
    )
