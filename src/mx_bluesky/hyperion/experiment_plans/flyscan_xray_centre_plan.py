from __future__ import annotations

from functools import partial
from pathlib import Path

import bluesky.plan_stubs as bps
import pydantic
from blueapi.core import BlueskyContext
from bluesky.utils import MsgGenerator
from dodal.devices.aperturescatterguard import (
    ApertureScatterguard,
)
from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
from dodal.devices.dcm import DCM
from dodal.devices.eiger import EigerDetector
from dodal.devices.fast_grid_scan import (
    PandAFastGridScan,
    set_fast_grid_scan_params,
)
from dodal.devices.flux import Flux
from dodal.devices.robot import BartRobot
from dodal.devices.s4_slit_gaps import S4SlitGaps
from dodal.devices.synchrotron import Synchrotron
from dodal.devices.undulator import Undulator
from dodal.devices.zebra.zebra import Zebra
from dodal.devices.zebra.zebra_controlled_shutter import ZebraShutter
from dodal.devices.zocalo.zocalo_results import (
    ZocaloResults,
)
from ophyd_async.fastcs.panda import HDFPanda

from mx_bluesky.common.plans.common_flyscan_xray_centre_plan import (
    FlyScanEssentialDevices,
    construct_beamline_specific_FGS_features,
    highest_level_flyscan_xray_centre,
)
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.hyperion.device_setup_plans.setup_panda import (
    disarm_panda_for_gridscan,
    set_panda_directory,
    setup_panda_for_flyscan,
)
from mx_bluesky.hyperion.device_setup_plans.setup_zebra import (
    setup_zebra_for_gridscan,
    setup_zebra_for_panda_flyscan,
    tidy_up_zebra_after_gridscan,
)
from mx_bluesky.hyperion.parameters.gridscan import HyperionSpecifiedThreeDGridScan
from mx_bluesky.hyperion.utils.context import device_composite_from_context


class SmargonSpeedException(Exception):
    pass


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class FlyScanXRayCentreComposite(FlyScanEssentialDevices):
    """All devices which are directly or indirectly required by this plan"""

    aperture_scatterguard: ApertureScatterguard
    attenuator: BinaryFilterAttenuator
    dcm: DCM
    eiger: EigerDetector
    flux: Flux
    s4_slit_gaps: S4SlitGaps
    undulator: Undulator
    synchrotron: Synchrotron
    zebra: Zebra
    zocalo: ZocaloResults
    panda: HDFPanda
    panda_fast_grid_scan: PandAFastGridScan
    robot: BartRobot
    sample_shutter: ZebraShutter


def create_devices(context: BlueskyContext) -> FlyScanXRayCentreComposite:
    """Creates the devices required for the plan and connect to them"""
    return device_composite_from_context(context, FlyScanXRayCentreComposite)


def hyperion_flyscan_xray_centre(
    composite: FlyScanXRayCentreComposite,
    parameters: HyperionSpecifiedThreeDGridScan,
) -> MsgGenerator:
    """Create the plan to run the grid scan based on provided parameters.

    The ispyb handler should be added to the whole gridscan as we want to capture errors
    at any point in it.

    Args:
        parameters (HyperionSpecifiedThreeDGridScan): The parameters to run the scan.

    Returns:
        Generator: The plan for the gridscan
    """
    feature_controlled = construct_hyperion_specific_features(composite, parameters)

    yield from highest_level_flyscan_xray_centre(
        composite, parameters, feature_controlled
    )


def construct_hyperion_specific_features(
    fgs_composite: FlyScanXRayCentreComposite,
    parameters: HyperionSpecifiedThreeDGridScan,
):
    """
    Get all the information needed to do the Hyperion-specific parts of the XRC flyscan.
    """

    signals_to_read_pre_collection = [
        fgs_composite.undulator.current_gap,
        fgs_composite.synchrotron.synchrotron_mode,
        fgs_composite.s4_slit_gaps.xgap,
        fgs_composite.s4_slit_gaps.ygap,
        fgs_composite.smargon.x,
        fgs_composite.smargon.y,
        fgs_composite.smargon.z,
        fgs_composite.dcm.energy_in_kev,
    ]

    signals_to_read_during_collection = [
        fgs_composite.aperture_scatterguard,
        fgs_composite.attenuator.actual_transmission,
        fgs_composite.flux.flux_reading,
        fgs_composite.dcm.energy_in_kev,
        fgs_composite.eiger.bit_depth,
    ]

    if parameters.features.use_panda_for_gridscan:
        setup_trigger = _panda_triggering_setup
        tidy_plan = _panda_tidy
        set_flyscan_params = partial(
            set_fast_grid_scan_params,
            fgs_composite.panda_fast_grid_scan,
            parameters.panda_FGS_params,
        )
        fgs_motors = fgs_composite.panda_fast_grid_scan

    else:
        setup_trigger = _zebra_triggering_setup
        tidy_plan = partial(_generic_tidy, group="flyscan_zebra_tidy", wait=True)
        set_flyscan_params = partial(
            set_fast_grid_scan_params,
            fgs_composite.zebra_fast_grid_scan,
            parameters.FGS_params,
        )
        fgs_motors = fgs_composite.zebra_fast_grid_scan
    return construct_beamline_specific_FGS_features(
        setup_trigger,
        tidy_plan,
        set_flyscan_params,
        fgs_motors,
        signals_to_read_pre_collection,
        signals_to_read_during_collection,
        plan_using_xrc_results=add_this,
    )


def _generic_tidy(
    fgs_composite: FlyScanXRayCentreComposite, group, wait=True
) -> MsgGenerator:
    LOGGER.info("Tidying up Zebra")
    yield from tidy_up_zebra_after_gridscan(
        fgs_composite.zebra, fgs_composite.sample_shutter, group=group, wait=wait
    )
    LOGGER.info("Tidying up Zocalo")
    # make sure we don't consume any other results
    yield from bps.unstage(fgs_composite.zocalo, group=group, wait=wait)


def _panda_tidy(fgs_composite: FlyScanXRayCentreComposite):
    group = "panda_flyscan_tidy"
    LOGGER.info("Disabling panda blocks")
    yield from disarm_panda_for_gridscan(fgs_composite.panda, group)
    yield from _generic_tidy(fgs_composite, group, False)
    yield from bps.wait(group, timeout=10)
    yield from bps.unstage(fgs_composite.panda)


def _zebra_triggering_setup(
    fgs_composite: FlyScanXRayCentreComposite,
    parameters: HyperionSpecifiedThreeDGridScan,
) -> MsgGenerator:
    yield from setup_zebra_for_gridscan(
        fgs_composite.zebra, fgs_composite.sample_shutter, wait=True
    )


def _panda_triggering_setup(
    fgs_composite: FlyScanXRayCentreComposite,
    parameters: HyperionSpecifiedThreeDGridScan,
) -> MsgGenerator:
    LOGGER.info("Setting up Panda for flyscan")

    run_up_distance_mm = yield from bps.rd(
        fgs_composite.panda_fast_grid_scan.run_up_distance_mm
    )

    # Set the time between x steps pv
    DEADTIME_S = 1e-6  # according to https://www.dectris.com/en/detectors/x-ray-detectors/eiger2/eiger2-for-synchrotrons/eiger2-x/

    time_between_x_steps_ms = (DEADTIME_S + parameters.exposure_time_s) * 1e3

    smargon_speed_limit_mm_per_s = yield from bps.rd(
        fgs_composite.smargon.x.max_velocity
    )

    sample_velocity_mm_per_s = (
        parameters.panda_FGS_params.x_step_size_mm * 1e3 / time_between_x_steps_ms
    )
    if sample_velocity_mm_per_s > smargon_speed_limit_mm_per_s:
        raise SmargonSpeedException(
            f"Smargon speed was calculated from x step size\
            {parameters.panda_FGS_params.x_step_size_mm}mm and\
            time_between_x_steps_ms {time_between_x_steps_ms} as\
            {sample_velocity_mm_per_s}mm/s. The smargon's speed limit is\
            {smargon_speed_limit_mm_per_s}mm/s."
        )
    else:
        LOGGER.info(
            f"Panda grid scan: Smargon speed set to {smargon_speed_limit_mm_per_s} mm/s"
            f" and using a run-up distance of {run_up_distance_mm}"
        )

    yield from bps.mv(
        fgs_composite.panda_fast_grid_scan.time_between_x_steps_ms,  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
        time_between_x_steps_ms,  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
    )

    directory_provider_root = Path(parameters.storage_directory)
    yield from set_panda_directory(directory_provider_root)

    yield from setup_panda_for_flyscan(
        fgs_composite.panda,
        parameters.panda_FGS_params,
        fgs_composite.smargon,
        parameters.exposure_time_s,
        time_between_x_steps_ms,
        sample_velocity_mm_per_s,
    )

    LOGGER.info("Setting up Zebra for panda flyscan")
    yield from setup_zebra_for_panda_flyscan(
        fgs_composite.zebra, fgs_composite.sample_shutter, wait=True
    )
