from __future__ import annotations

import pydantic
from bluesky.utils import MsgGenerator
from dodal.devices.aperturescatterguard import ApertureScatterguard
from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
from dodal.devices.backlight import Backlight
from dodal.devices.dcm import DCM
from dodal.devices.detector.detector_motion import DetectorMotion
from dodal.devices.eiger import EigerDetector
from dodal.devices.fast_grid_scan import PandAFastGridScan, ZebraFastGridScan
from dodal.devices.flux import Flux
from dodal.devices.i03.beamstop import Beamstop
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.oav.pin_image_recognition import PinTipDetection
from dodal.devices.robot import BartRobot
from dodal.devices.s4_slit_gaps import S4SlitGaps
from dodal.devices.smargon import Smargon
from dodal.devices.synchrotron import Synchrotron
from dodal.devices.undulator import Undulator
from dodal.devices.xbpm_feedback import XBPMFeedback
from dodal.devices.zebra.zebra import Zebra
from dodal.devices.zebra.zebra_controlled_shutter import ZebraShutter
from dodal.devices.zocalo import ZocaloResults
from ophyd_async.fastcs.panda import HDFPanda

from mx_bluesky.common.external_interaction.callbacks.common.grid_detection_callback import (
    GridDetectionCallback,
    GridParamUpdate,
)
from mx_bluesky.common.parameters.constants import OavConstants
from mx_bluesky.common.plans.common_grid_detect_then_xray_centre_plan import (
    GridDetectThenXRayCentreComposite,
    grid_detect_then_xray_centre,
)
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan import (
    flyscan_xray_centre_no_move,
)
from mx_bluesky.hyperion.parameters.device_composites import (
    HyperionFlyScanXRayCentreComposite,
)
from mx_bluesky.hyperion.parameters.gridscan import (
    GridScanWithEdgeDetect,
    HyperionSpecifiedThreeDGridScan,
)


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class HyperionGridDetectThenXRayCentreComposite(GridDetectThenXRayCentreComposite):
    """All devices which are directly or indirectly required by this plan"""

    aperture_scatterguard: ApertureScatterguard
    attenuator: BinaryFilterAttenuator
    backlight: Backlight
    beamstop: Beamstop
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


def create_parameters_for_flyscan_xray_centre(
    grid_scan_with_edge_params: GridScanWithEdgeDetect,
    grid_parameters: GridParamUpdate,
) -> HyperionSpecifiedThreeDGridScan:
    params_json = grid_scan_with_edge_params.model_dump()
    params_json.update(grid_parameters)
    flyscan_xray_centre_parameters = HyperionSpecifiedThreeDGridScan(**params_json)
    LOGGER.info(f"Parameters for FGS: {flyscan_xray_centre_parameters}")
    return flyscan_xray_centre_parameters


def hyperion_grid_detect_then_xray_centre(
    composite: HyperionGridDetectThenXRayCentreComposite,
    parameters: GridScanWithEdgeDetect,
    oav_config: str = OavConstants.OAV_CONFIG_JSON,
) -> MsgGenerator:
    """
    A plan which combines the collection of snapshots from the OAV and the determination
    of the grid dimensions to use for the following grid scan.
    """
    grid_params_callback = GridDetectionCallback()
    flyscan_xrc_plan = flyscan_xray_centre_no_move(
        HyperionFlyScanXRayCentreComposite(
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
    yield from grid_detect_then_xray_centre(
        composite, parameters, flyscan_xrc_plan, oav_config
    )
