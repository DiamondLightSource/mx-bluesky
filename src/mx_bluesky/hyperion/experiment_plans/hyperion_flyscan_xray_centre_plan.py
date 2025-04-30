from __future__ import annotations

from functools import partial
from pathlib import Path

import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.devices.fast_grid_scan import (
    set_fast_grid_scan_params,
)

from mx_bluesky.common.plans.common_flyscan_xray_centre_plan import (
    construct_beamline_specific_FGS_features,
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
from mx_bluesky.hyperion.parameters.device_composites import (
    HyperionFlyScanXRayCentreComposite,
)
from mx_bluesky.hyperion.parameters.gridscan import HyperionSpecifiedThreeDGridScan


class SmargonSpeedException(Exception):
    pass


def construct_hyperion_specific_features(
    fgs_composite: HyperionFlyScanXRayCentreComposite,
    parameters: HyperionSpecifiedThreeDGridScan,
):
    """
    Get all the information needed to do the Hyperion-specific parts of the XRC flyscan.
    """

    signals_to_read_pre_flyscan = [
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
        setup_trigger_plan = _panda_triggering_setup
        tidy_plan = _panda_tidy
        set_flyscan_params_plan = partial(
            set_fast_grid_scan_params,
            fgs_composite.panda_fast_grid_scan,
            parameters.panda_FGS_params,
        )
        fgs_motors = fgs_composite.panda_fast_grid_scan

    else:
        setup_trigger_plan = _zebra_triggering_setup
        tidy_plan = partial(_generic_tidy, group="flyscan_zebra_tidy", wait=True)
        set_flyscan_params_plan = partial(
            set_fast_grid_scan_params,
            fgs_composite.zebra_fast_grid_scan,
            parameters.FGS_params,
        )
        fgs_motors = fgs_composite.zebra_fast_grid_scan
    return construct_beamline_specific_FGS_features(
        setup_trigger_plan,
        tidy_plan,
        set_flyscan_params_plan,
        fgs_motors,
        signals_to_read_pre_flyscan,
        signals_to_read_during_collection,
        get_xrc_results_from_zocalo=True,
    )


def _generic_tidy(
    fgs_composite: HyperionFlyScanXRayCentreComposite, group, wait=True
) -> MsgGenerator:
    LOGGER.info("Tidying up Zebra")
    yield from tidy_up_zebra_after_gridscan(
        fgs_composite.zebra, fgs_composite.sample_shutter, group=group, wait=wait
    )
    LOGGER.info("Tidying up Zocalo")
    # make sure we don't consume any other results
    yield from bps.unstage(fgs_composite.zocalo, group=group, wait=wait)

    # Turn off dev/shm streaming to avoid filling disk, see https://github.com/DiamondLightSource/hyperion/issues/1395
    LOGGER.info("Turning off Eiger dev/shm streaming")
    yield from bps.abs_set(fgs_composite.eiger.odin.fan.dev_shm_enable, 0)  # type: ignore # Fix types in ophyd-async (https://github.com/DiamondLightSource/mx-bluesky/issues/855)


def _panda_tidy(fgs_composite: HyperionFlyScanXRayCentreComposite):
    group = "panda_flyscan_tidy"
    LOGGER.info("Disabling panda blocks")
    yield from disarm_panda_for_gridscan(fgs_composite.panda, group)
    yield from _generic_tidy(fgs_composite, group, False)
    yield from bps.wait(group, timeout=10)
    yield from bps.unstage(fgs_composite.panda)


def _zebra_triggering_setup(
    fgs_composite: HyperionFlyScanXRayCentreComposite,
    parameters: HyperionSpecifiedThreeDGridScan,
) -> MsgGenerator:
    yield from setup_zebra_for_gridscan(
        fgs_composite.zebra, fgs_composite.sample_shutter, wait=True
    )


def _panda_triggering_setup(
    fgs_composite: HyperionFlyScanXRayCentreComposite,
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
