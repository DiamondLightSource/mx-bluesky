from __future__ import annotations

import dataclasses
from pathlib import Path

from blueapi.core import BlueskyContext, MsgGenerator
from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp
from dodal.devices.aperturescatterguard import ApertureScatterguard
from dodal.devices.attenuator import Attenuator
from dodal.devices.backlight import Backlight, BacklightPosition
from dodal.devices.dcm import DCM
from dodal.devices.detector.detector_motion import DetectorMotion
from dodal.devices.eiger import EigerDetector
from dodal.devices.fast_grid_scan import PandAFastGridScan, ZebraFastGridScan
from dodal.devices.flux import Flux
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.oav.oav_parameters import OAV_CONFIG_JSON, OAVParameters
from dodal.devices.oav.pin_image_recognition import PinTipDetection
from dodal.devices.robot import BartRobot
from dodal.devices.s4_slit_gaps import S4SlitGaps
from dodal.devices.smargon import Smargon
from dodal.devices.synchrotron import Synchrotron
from dodal.devices.undulator import Undulator
from dodal.devices.xbpm_feedback import XBPMFeedback
from dodal.devices.zebra import Zebra
from dodal.devices.zebra_controlled_shutter import ZebraShutter
from dodal.devices.zocalo import ZocaloResults
from ophyd_async.fastcs.panda import HDFPanda

from mx_bluesky.hyperion.device_setup_plans.manipulate_sample import (
    move_aperture_if_required,
)
from mx_bluesky.hyperion.device_setup_plans.utils import (
    start_preparing_data_collection_then_do_plan,
)
from mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan import (
    FlyScanXRayCentreComposite as FlyScanXRayCentreComposite,
)
from mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan import (
    flyscan_xray_centre,
)
from mx_bluesky.hyperion.experiment_plans.oav_grid_detection_plan import (
    OavGridDetectionComposite,
    grid_detection_plan,
)
from mx_bluesky.hyperion.external_interaction.callbacks.grid_detection_callback import (
    GridDetectionCallback,
    GridParamUpdate,
)
from mx_bluesky.hyperion.external_interaction.callbacks.xray_centre.ispyb_callback import (
    ispyb_activation_wrapper,
)
from mx_bluesky.hyperion.log import LOGGER
from mx_bluesky.hyperion.parameters.constants import CONST
from mx_bluesky.hyperion.parameters.gridscan import (
    GridScanWithEdgeDetect,
    ThreeDGridScan,
)
from mx_bluesky.hyperion.utils.context import device_composite_from_context


@dataclasses.dataclass
class GridDetectThenXRayCentreComposite:
    """All devices which are directly or indirectly required by this plan"""

    aperture_scatterguard: ApertureScatterguard
    attenuator: Attenuator
    backlight: Backlight
    dcm: DCM
    detector_motion: DetectorMotion
    eiger: EigerDetector
    zebra_fast_grid_scan: ZebraFastGridScan
    flux: Flux
    oav: OAV
    pin_tip_detection: PinTipDetection
    smargon: Smargon
    synchrotron: Synchrotron
    s4_slit_gaps: S4SlitGaps
    undulator: Undulator
    xbpm_feedback: XBPMFeedback
    zebra: Zebra
    zocalo: ZocaloResults
    panda: HDFPanda
    panda_fast_grid_scan: PandAFastGridScan
    robot: BartRobot
    sample_shutter: ZebraShutter


def create_devices(context: BlueskyContext) -> GridDetectThenXRayCentreComposite:
    return device_composite_from_context(context, GridDetectThenXRayCentreComposite)


def create_parameters_for_flyscan_xray_centre(
    grid_scan_with_edge_params: GridScanWithEdgeDetect,
    grid_parameters: GridParamUpdate,
) -> ThreeDGridScan:
    params_json = grid_scan_with_edge_params.model_dump()
    params_json.update(grid_parameters)
    flyscan_xray_centre_parameters = ThreeDGridScan(**params_json)
    LOGGER.info(f"Parameters for FGS: {flyscan_xray_centre_parameters}")
    return flyscan_xray_centre_parameters


def detect_grid_and_do_gridscan(
    composite: GridDetectThenXRayCentreComposite,
    parameters: GridScanWithEdgeDetect,
    oav_params: OAVParameters,
):
    snapshot_template = f"{parameters.detector_params.prefix}_{parameters.detector_params.run_number}_{{angle}}"

    grid_params_callback = GridDetectionCallback(composite.oav.parameters)

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
            grid_width_microns=parameters.grid_width_um,
        )

    yield from run_grid_detection_plan(
        oav_params,
        snapshot_template,
        parameters.snapshot_directory,
    )

    yield from bps.abs_set(
        composite.backlight, BacklightPosition.OUT, group=CONST.WAIT.GRID_READY_FOR_DC
    )

    yield from move_aperture_if_required(
        composite.aperture_scatterguard,
        parameters.selected_aperture,
        group=CONST.WAIT.GRID_READY_FOR_DC,
    )

    yield from flyscan_xray_centre(
        FlyScanXRayCentreComposite(
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
        ),
        create_parameters_for_flyscan_xray_centre(
            parameters, grid_params_callback.get_grid_parameters()
        ),
    )


def grid_detect_then_xray_centre(
    composite: GridDetectThenXRayCentreComposite,
    parameters: GridScanWithEdgeDetect,
    oav_config: str = OAV_CONFIG_JSON,
) -> MsgGenerator:
    """
    A plan which combines the collection of snapshots from the OAV and the determination
    of the grid dimensions to use for the following grid scan.
    """

    eiger: EigerDetector = composite.eiger

    eiger.set_detector_parameters(parameters.detector_params)

    oav_params = OAVParameters("xrayCentring", oav_config)

    plan_to_perform = ispyb_activation_wrapper(
        detect_grid_and_do_gridscan(
            composite,
            parameters,
            oav_params,
        ),
        parameters,
    )

    return start_preparing_data_collection_then_do_plan(
        eiger,
        composite.detector_motion,
        parameters.detector_params.detector_distance,
        plan_to_perform,
        group=CONST.WAIT.GRID_READY_FOR_DC,
    )