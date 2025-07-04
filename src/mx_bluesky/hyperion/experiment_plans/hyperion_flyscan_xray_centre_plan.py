from __future__ import annotations

from collections.abc import Callable
from functools import partial
from pathlib import Path

import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.devices.fast_grid_scan import (
    set_fast_grid_scan_params,
)

from mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan import (
    construct_beamline_specific_FGS_features,
)
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.hyperion.device_setup_plans.setup_panda import (
    disarm_panda_for_gridscan,
    set_panda_directory,
    setup_panda_for_flyscan,
)
from mx_bluesky.hyperion.device_setup_plans.setup_zebra import (
    setup_zebra_for_panda_flyscan,
)
from mx_bluesky.hyperion.parameters.device_composites import (
    HyperionFlyScanXRayCentreComposite,
)
from mx_bluesky.hyperion.parameters.gridscan import HyperionSpecifiedThreeDGridScan
from mx_bluesky.phase1_zebra.device_setup_plans.setup_zebra import (
    setup_zebra_for_gridscan,
    tidy_up_zebra_after_gridscan,
)


class SmargonSpeedException(Exception):
    pass


def construct_hyperion_specific_features(
    xrc_composite: HyperionFlyScanXRayCentreComposite,
    xrc_parameters: HyperionSpecifiedThreeDGridScan,
):
    """
    Get all the information needed to do the Hyperion-specific parts of the XRC flyscan.
    """
    signals_to_read_pre_flyscan = [
        xrc_composite.undulator.current_gap,
        xrc_composite.synchrotron.synchrotron_mode,
        xrc_composite.s4_slit_gaps.xgap,
        xrc_composite.s4_slit_gaps.ygap,
        xrc_composite.smargon.x,
        xrc_composite.smargon.y,
        xrc_composite.smargon.z,
        xrc_composite.dcm.energy_in_kev,
    ]

    signals_to_read_during_collection = [
        xrc_composite.aperture_scatterguard,
        xrc_composite.attenuator.actual_transmission,
        xrc_composite.flux.flux_reading,
        xrc_composite.dcm.energy_in_kev,
        xrc_composite.eiger.bit_depth,
    ]

    setup_trigger_plan: Callable[..., MsgGenerator]

    if xrc_parameters.features.use_panda_for_gridscan:
        setup_trigger_plan = _panda_triggering_setup
        tidy_plan = partial(_panda_tidy, xrc_composite)
        set_flyscan_params_plan = partial(
            set_fast_grid_scan_params,
            xrc_composite.panda_fast_grid_scan,
            xrc_parameters.panda_FGS_params,
        )
        fgs_motors = xrc_composite.panda_fast_grid_scan

    else:
        setup_trigger_plan = setup_zebra_for_gridscan
        tidy_plan = partial(
            tidy_up_zebra_after_gridscan,
            xrc_composite.zebra,
            xrc_composite.sample_shutter,
            group="flyscan_zebra_tidy",
            wait=True,
        )
        set_flyscan_params_plan = partial(
            set_fast_grid_scan_params,
            xrc_composite.zebra_fast_grid_scan,
            xrc_parameters.FGS_params,
        )
        fgs_motors = xrc_composite.zebra_fast_grid_scan
    return construct_beamline_specific_FGS_features(
        setup_trigger_plan,
        tidy_plan,
        set_flyscan_params_plan,
        fgs_motors,
        signals_to_read_pre_flyscan,
        signals_to_read_during_collection,
        get_xrc_results_from_zocalo=True,
    )


def _panda_tidy(xrc_composite: HyperionFlyScanXRayCentreComposite):
    group = "panda_flyscan_tidy"
    LOGGER.info("Disabling panda blocks")
    yield from disarm_panda_for_gridscan(xrc_composite.panda, group)
    yield from tidy_up_zebra_after_gridscan(
        xrc_composite.zebra, xrc_composite.sample_shutter, group=group, wait=False
    )
    yield from bps.wait(group, timeout=10)
    yield from bps.unstage(xrc_composite.panda)


def _panda_triggering_setup(
    xrc_composite: HyperionFlyScanXRayCentreComposite,
    parameters: HyperionSpecifiedThreeDGridScan,
) -> MsgGenerator:
    LOGGER.info("Setting up Panda for flyscan")

    run_up_distance_mm = yield from bps.rd(
        xrc_composite.panda_fast_grid_scan.run_up_distance_mm
    )

    # Set the time between x steps pv
    DEADTIME_S = 1e-6  # according to https://www.dectris.com/en/detectors/x-ray-detectors/eiger2/eiger2-for-synchrotrons/eiger2-x/

    time_between_x_steps_ms = (DEADTIME_S + parameters.exposure_time_s) * 1e3

    smargon_speed_limit_mm_per_s = yield from bps.rd(
        xrc_composite.smargon.x.max_velocity
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
        xrc_composite.panda_fast_grid_scan.time_between_x_steps_ms,  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
        time_between_x_steps_ms,  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
    )

    directory_provider_root = Path(parameters.storage_directory)
    yield from set_panda_directory(directory_provider_root)

    yield from setup_panda_for_flyscan(
        xrc_composite.panda,
        parameters.panda_FGS_params,
        xrc_composite.smargon,
        parameters.exposure_time_s,
        time_between_x_steps_ms,
        sample_velocity_mm_per_s,
    )

    LOGGER.info("Setting up Zebra for panda flyscan")
    yield from setup_zebra_for_panda_flyscan(
        xrc_composite.zebra, xrc_composite.sample_shutter, wait=True
    )
