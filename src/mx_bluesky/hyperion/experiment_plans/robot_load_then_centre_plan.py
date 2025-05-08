from __future__ import annotations

from math import isclose
from typing import cast

import pydantic
from blueapi.core import BlueskyContext
from bluesky import plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.devices.aperturescatterguard import ApertureScatterguard
from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
from dodal.devices.backlight import Backlight
from dodal.devices.detector.detector_motion import DetectorMotion
from dodal.devices.eiger import EigerDetector
from dodal.devices.fast_grid_scan import PandAFastGridScan, ZebraFastGridScan
from dodal.devices.flux import Flux
from dodal.devices.focusing_mirror import FocusingMirrorWithStripes, MirrorVoltages
from dodal.devices.i03 import Beamstop
from dodal.devices.i03.dcm import DCM
from dodal.devices.i03.undulator_dcm import UndulatorDCM
from dodal.devices.motors import XYZPositioner
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.oav.pin_image_recognition import PinTipDetection
from dodal.devices.robot import BartRobot, SampleLocation
from dodal.devices.s4_slit_gaps import S4SlitGaps
from dodal.devices.smargon import Smargon
from dodal.devices.synchrotron import Synchrotron
from dodal.devices.thawer import Thawer
from dodal.devices.undulator import Undulator
from dodal.devices.webcam import Webcam
from dodal.devices.xbpm_feedback import XBPMFeedback
from dodal.devices.zebra.zebra import Zebra
from dodal.devices.zebra.zebra_controlled_shutter import ZebraShutter
from dodal.devices.zocalo import ZocaloResults
from dodal.log import LOGGER
from ophyd_async.fastcs.panda import HDFPanda

from mx_bluesky.common.parameters.constants import OavConstants
from mx_bluesky.hyperion.device_setup_plans.utils import (
    fill_in_energy_if_not_supplied,
    start_preparing_data_collection_then_do_plan,
)
from mx_bluesky.hyperion.experiment_plans.grid_detect_then_xray_centre_plan import (
    GridDetectThenXRayCentreComposite,
)
from mx_bluesky.hyperion.experiment_plans.pin_centre_then_xray_centre_plan import (
    pin_centre_then_flyscan_plan,
)
from mx_bluesky.hyperion.experiment_plans.robot_load_and_change_energy import (
    RobotLoadAndEnergyChangeComposite,
    pin_already_loaded,
    robot_load_and_change_energy_plan,
)
from mx_bluesky.hyperion.experiment_plans.set_energy_plan import (
    SetEnergyComposite,
    set_energy_plan,
)
from mx_bluesky.hyperion.parameters.constants import CONST
from mx_bluesky.hyperion.parameters.robot_load import RobotLoadThenCentre


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class RobotLoadThenCentreComposite:
    # common fields
    xbpm_feedback: XBPMFeedback
    attenuator: BinaryFilterAttenuator

    # GridDetectThenXRayCentreComposite fields
    aperture_scatterguard: ApertureScatterguard
    backlight: Backlight
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
    zebra: Zebra
    zocalo: ZocaloResults
    panda: HDFPanda
    panda_fast_grid_scan: PandAFastGridScan
    thawer: Thawer
    sample_shutter: ZebraShutter

    # SetEnergyComposite fields
    vfm: FocusingMirrorWithStripes
    mirror_voltages: MirrorVoltages
    dcm: DCM
    undulator_dcm: UndulatorDCM

    # RobotLoad fields
    robot: BartRobot
    webcam: Webcam
    lower_gonio: XYZPositioner
    beamstop: Beamstop


def create_devices(context: BlueskyContext) -> RobotLoadThenCentreComposite:
    from mx_bluesky.common.utils.context import device_composite_from_context

    return device_composite_from_context(context, RobotLoadThenCentreComposite)


def _flyscan_plan_from_robot_load_params(
    composite: RobotLoadThenCentreComposite,
    params: RobotLoadThenCentre,
    oav_config_file: str = OavConstants.OAV_CONFIG_JSON,
):
    yield from pin_centre_then_flyscan_plan(
        cast(GridDetectThenXRayCentreComposite, composite),
        params.pin_centre_then_xray_centre_params,
        oav_config_file,
    )


def _robot_load_then_flyscan_plan(
    composite: RobotLoadThenCentreComposite,
    params: RobotLoadThenCentre,
    oav_config_file: str = OavConstants.OAV_CONFIG_JSON,
):
    yield from robot_load_and_change_energy_plan(
        cast(RobotLoadAndEnergyChangeComposite, composite),
        params.robot_load_params,
    )

    yield from _flyscan_plan_from_robot_load_params(composite, params, oav_config_file)


def robot_load_then_xray_centre(
    composite: RobotLoadThenCentreComposite,
    parameters: RobotLoadThenCentre,
    oav_config_file: str = OavConstants.OAV_CONFIG_JSON,
) -> MsgGenerator:
    """Perform pin-tip detection followed by a flyscan to determine centres of interest.
    Performs a robot load if necessary."""
    eiger: EigerDetector = composite.eiger

    # TODO: get these from one source of truth #254
    assert parameters.sample_puck is not None
    assert parameters.sample_pin is not None

    sample_location = SampleLocation(parameters.sample_puck, parameters.sample_pin)

    doing_sample_load = not (
        yield from pin_already_loaded(composite.robot, sample_location)
    )

    current_chi = yield from bps.rd(composite.smargon.chi)
    LOGGER.info(f"Read back current smargon chi of {current_chi} degrees.")
    doing_chi_change = parameters.chi_start_deg is not None and not isclose(
        current_chi, parameters.chi_start_deg, abs_tol=0.001
    )

    if doing_sample_load:
        LOGGER.info("Pin not loaded, loading and centring")
        plan = _robot_load_then_flyscan_plan(composite, parameters, oav_config_file)
    else:
        # Robot load normally sets the energy so we should do this explicitly if no load is
        # being done
        demand_energy_ev = parameters.demand_energy_ev
        LOGGER.info(f"Setting the energy to {demand_energy_ev}eV")
        yield from set_energy_plan(
            demand_energy_ev, cast(SetEnergyComposite, composite)
        )

        if doing_chi_change:
            plan = _flyscan_plan_from_robot_load_params(
                composite, parameters, oav_config_file
            )
            LOGGER.info("Pin already loaded but chi changed so centring")
        else:
            LOGGER.info("Pin already loaded and chi not changed so doing nothing")
            return

    detector_params = yield from fill_in_energy_if_not_supplied(
        composite.dcm, parameters.detector_params
    )

    eiger.set_detector_parameters(detector_params)

    yield from start_preparing_data_collection_then_do_plan(
        composite.beamstop,
        eiger,
        composite.detector_motion,
        parameters.detector_distance_mm,
        plan,
        group=CONST.WAIT.GRID_READY_FOR_DC,
    )
