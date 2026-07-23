from __future__ import annotations

from pathlib import Path

from bluesky import plan_stubs as bps
from bluesky.utils import MsgGenerator
from daq_config_server.models.feature_settings.hyperion_feature_settings import (
    HyperionFeatureSettings,
)
from dodal.devices.fast_grid_scan import (
    PandAFastGridScan,
    PandAGridScanParams,
    set_fast_grid_scan_params,
)

from mx_bluesky.common.device_setup_plans.gridscan import tidy_up_zebra_after_gridscan
from mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan import (
    TSetupParameters,
)
from mx_bluesky.common.parameters.components import DiffractionExperiment
from mx_bluesky.common.parameters.gridscan import GridScanParams
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.hyperion.blueapi.composites import (
    HyperionInternalGridDetectThenXRayCentreComposite,
)
from mx_bluesky.hyperion.device_setup_plans.setup_panda import (
    disarm_panda_for_gridscan,
    set_panda_directory,
    setup_panda_for_flyscan,
)
from mx_bluesky.hyperion.device_setup_plans.setup_zebra import (
    setup_zebra_for_panda_flyscan,
)
from mx_bluesky.hyperion.experiment_plans.hyperion_beamline_specific import (
    SmargonSpeedError,
)


def set_panda_fgs_params(
    panda_fast_grid_scan: PandAFastGridScan,
    expt_params: TSetupParameters,
    grid_scan_params: GridScanParams,
    settings: HyperionFeatureSettings,
) -> MsgGenerator:
    panda_fgs_params = _panda_fast_gridscan_params(
        expt_params, grid_scan_params, settings
    )
    yield from set_fast_grid_scan_params(panda_fast_grid_scan, panda_fgs_params)


def panda_triggering_setup(
    xrc_composite: HyperionInternalGridDetectThenXRayCentreComposite,
    parameters: TSetupParameters,
    grid_scan_parameters: GridScanParams,
    settings: HyperionFeatureSettings,
) -> MsgGenerator:
    LOGGER.info("Setting up Panda for flyscan")

    run_up_distance_mm = yield from bps.rd(
        xrc_composite.panda_fast_grid_scan.run_up_distance_mm
    )

    detector_deadtime_s = 1e-4  # This value was empirically found to be safer than the documented deadtime in the Eiger manual

    time_between_x_steps_ms = (detector_deadtime_s + parameters.exposure_time_s) * 1e3

    smargon_speed_limit_mm_per_s = yield from bps.rd(xrc_composite.gonio.x.max_velocity)

    panda_params = _panda_fast_gridscan_params(
        parameters, grid_scan_parameters, settings
    )
    sample_velocity_mm_per_s = (
        panda_params.x_step_size_mm * 1e3 / time_between_x_steps_ms
    )
    if sample_velocity_mm_per_s > smargon_speed_limit_mm_per_s:
        raise SmargonSpeedError(
            f"Smargon speed was calculated from x step size\
            {panda_params.x_step_size_mm}mm and\
            time_between_x_steps_ms {time_between_x_steps_ms} as\
            {sample_velocity_mm_per_s}mm/s. The smargon's speed limit is\
            {smargon_speed_limit_mm_per_s}mm/s."
        )
    else:
        LOGGER.info(
            f"Panda grid scan: Smargon speed set to {sample_velocity_mm_per_s} mm/s"
            f" and using a run-up distance of {run_up_distance_mm}"
        )

    yield from bps.mv(
        xrc_composite.panda_fast_grid_scan.time_between_x_steps_ms,
        time_between_x_steps_ms,
    )

    directory_provider_root = Path(parameters.storage_directory)
    yield from set_panda_directory(directory_provider_root)

    yield from setup_panda_for_flyscan(
        xrc_composite.panda,
        panda_params,
        xrc_composite.gonio,
        parameters.exposure_time_s,
        time_between_x_steps_ms,
        sample_velocity_mm_per_s,
    )

    LOGGER.info("Setting up Zebra for panda flyscan")
    yield from setup_zebra_for_panda_flyscan(
        xrc_composite.zebra, xrc_composite.sample_shutter, wait=True
    )


def _panda_fast_gridscan_params(
    expt_params: DiffractionExperiment,
    grid_scan_params: GridScanParams,
    settings: HyperionFeatureSettings,
) -> PandAGridScanParams:
    if grid_scan_params.y_steps[0] % 2 and grid_scan_params.y_steps[1] > 0:
        # See https://github.com/DiamondLightSource/hyperion/issues/1118 for explanation
        raise OddYStepsError("The number of Y steps must be even for a PandA gridscan")
    return PandAGridScanParams(
        x_steps=grid_scan_params.x_steps,
        y_steps=grid_scan_params.y_steps[0],
        z_steps=grid_scan_params.y_steps[1],
        x_step_size_mm=grid_scan_params.x_step_size_um / 1000,
        y_step_size_mm=grid_scan_params.y_step_sizes_um[0] / 1000,
        z_step_size_mm=grid_scan_params.y_step_sizes_um[1] / 1000,
        x_start_mm=grid_scan_params.x_start_um / 1000,
        y1_start_mm=grid_scan_params.y_starts_um[0] / 1000,
        z1_start_mm=grid_scan_params.z_starts_um[0] / 1000,
        y2_start_mm=grid_scan_params.y_starts_um[1] / 1000,
        z2_start_mm=grid_scan_params.z_starts_um[1] / 1000,
        set_stub_offsets=settings.SET_STUB_OFFSETS,
        run_up_distance_mm=settings.PANDA_RUNUP_DISTANCE_MM,
        transmission_fraction=expt_params.transmission_frac,
    )


class OddYStepsError(Exception): ...


def panda_tidy(xrc_composite: HyperionInternalGridDetectThenXRayCentreComposite):
    group = "panda_flyscan_tidy"
    LOGGER.info("Disabling panda blocks")
    yield from disarm_panda_for_gridscan(xrc_composite.panda, group)
    yield from tidy_up_zebra_after_gridscan(
        xrc_composite.zebra, xrc_composite.sample_shutter, group=group, wait=False
    )
    yield from bps.unstage(xrc_composite.panda, group=group)
    yield from bps.wait(group, timeout=10)
