from __future__ import annotations

from math import isclose
from typing import cast

import pydantic
from bluesky import plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.devices.beamlines.i03.undulator_dcm import UndulatorDCM
from dodal.devices.detector import DetectorParams
from dodal.devices.focusing_mirror import FocusingMirrorWithStripes, MirrorVoltages
from dodal.devices.motors import XYZStage
from dodal.devices.robot import BartRobot, SampleLocation
from dodal.devices.thawer import Thawer
from dodal.devices.webcam import Webcam
from dodal.log import LOGGER

from mx_bluesky.common.device_setup_plans.gridscan.beamline_specific import (
    BeamlineSpecificFGSFeatures,
)
from mx_bluesky.common.device_setup_plans.utils import (
    start_preparing_data_collection_then_do_plan,
)
from mx_bluesky.common.parameters.constants import OavConstants
from mx_bluesky.hyperion.blueapi.composites import (
    HyperionGridDetectThenXRayCentreComposite,
)
from mx_bluesky.hyperion.device_setup_plans.utils import (
    fill_in_energy_if_not_supplied,
)
from mx_bluesky.hyperion.experiment_plans.hyperion_beamline_specific import (
    construct_hyperion_specific_features,
)
from mx_bluesky.hyperion.experiment_plans.pin_centre_then_gridscan_plan import (
    pin_centre_then_gridscan_plan,
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
from mx_bluesky.hyperion.parameters.gridscan import (
    create_detector_params_for_grid_scan_with_hyperion_feature_settings,
)
from mx_bluesky.hyperion.parameters.robot_load import RobotLoadThenCentre


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class RobotLoadThenCentreComposite(HyperionGridDetectThenXRayCentreComposite):
    """
    Extends the grid detect and grid scan devices to include additional devices needed for
    robot load and changing energy.
    """

    # SetEnergyComposite fields
    vfm: FocusingMirrorWithStripes
    mirror_voltages: MirrorVoltages
    undulator_dcm: UndulatorDCM

    # RobotLoad fields
    robot: BartRobot
    thawer: Thawer
    webcam: Webcam
    lower_gonio: XYZStage


def _flyscan_plan_from_robot_load_params(
    beamline_specific: BeamlineSpecificFGSFeatures,
    composite: HyperionGridDetectThenXRayCentreComposite,
    params: RobotLoadThenCentre,
    detector_params: DetectorParams,
    oav_config_file: str = OavConstants.OAV_CONFIG_JSON,
):
    yield from pin_centre_then_gridscan_plan(
        beamline_specific,
        composite,
        params.pin_centre_then_xray_centre_params,
        detector_params,
        oav_config_file,
    )


def _robot_load_then_flyscan_plan(
    beamline_specific: BeamlineSpecificFGSFeatures,
    composite: RobotLoadThenCentreComposite,
    grid_detect_composite: HyperionGridDetectThenXRayCentreComposite,
    params: RobotLoadThenCentre,
    detector_params: DetectorParams,
    oav_config_file: str = OavConstants.OAV_CONFIG_JSON,
):
    yield from robot_load_and_change_energy_plan(
        cast(RobotLoadAndEnergyChangeComposite, composite),
        params.robot_load_params,
    )

    yield from _flyscan_plan_from_robot_load_params(
        beamline_specific,
        grid_detect_composite,
        params,
        detector_params,
        oav_config_file,
    )


def robot_load_then_xray_centre(
    composite: RobotLoadThenCentreComposite,
    parameters: RobotLoadThenCentre,
    oav_config_file: str = OavConstants.OAV_CONFIG_JSON,
) -> MsgGenerator:
    """Perform pin-tip detection followed by a flyscan to determine centres of interest.
    Performs a robot load if necessary."""
    # TODO: get these from one source of truth #254
    assert parameters.sample_puck is not None
    assert parameters.sample_pin is not None

    sample_location = SampleLocation(parameters.sample_puck, parameters.sample_pin)

    doing_sample_load = not (
        yield from pin_already_loaded(composite.robot, sample_location)
    )

    current_chi = yield from bps.rd(composite.gonio.chi)
    LOGGER.info(f"Read back current smargon chi of {current_chi} degrees.")
    doing_chi_change = parameters.chi_start_deg is not None and not isclose(
        current_chi, parameters.chi_start_deg, abs_tol=0.001
    )

    # TODO this is no longer used in production since r_l_t_x_c is now only
    # ever called via agamemnon, so energy is always specified
    # https://github.com/DiamondLightSource/mx-bluesky/issues/1792
    detector_params = (
        create_detector_params_for_grid_scan_with_hyperion_feature_settings(parameters)
    )
    detector_params = yield from fill_in_energy_if_not_supplied(
        composite.dcm, detector_params
    )

    grid_detect_and_gridscan_composite = composite

    beamline_specific = construct_hyperion_specific_features(
        grid_detect_and_gridscan_composite, parameters
    )

    if doing_sample_load:
        LOGGER.info("Pin not loaded, loading and centring")
        plan = _robot_load_then_flyscan_plan(
            beamline_specific,
            composite,
            grid_detect_and_gridscan_composite,
            parameters,
            detector_params,
            oav_config_file,
        )
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
                beamline_specific,
                grid_detect_and_gridscan_composite,
                parameters,
                detector_params,
                oav_config_file,
            )
            LOGGER.info("Pin already loaded but chi changed so centring")
        else:
            LOGGER.info("Pin already loaded and chi not changed so doing nothing")
            return

    yield from start_preparing_data_collection_then_do_plan(
        beamline_specific,
        detector_params,
        grid_detect_and_gridscan_composite,
        parameters.detector_distance_mm,
        plan,
        group=CONST.WAIT.GRID_READY_FOR_DC,
    )
