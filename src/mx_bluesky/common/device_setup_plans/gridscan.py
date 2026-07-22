from __future__ import annotations

from bluesky.utils import MsgGenerator
from dodal.devices.fast_grid_scan import (
    FastGridScanThreeD,
    PandAFastGridScan,
    PandAGridScanParams,
    ZebraGridScanParamsThreeD,
    set_fast_grid_scan_params,
)

from mx_bluesky.common.parameters.components import DiffractionExperiment
from mx_bluesky.common.parameters.gridscan import GridScanParams


def set_zebra_fgs_3d_params(
    fast_grid_scan: FastGridScanThreeD[ZebraGridScanParamsThreeD],
    expt_params: DiffractionExperiment,
    grid_scan_params: GridScanParams,
    set_stub_offsets: bool = False,
) -> MsgGenerator:
    zebra_fgs_params = _fast_gridscan_3d_params(
        expt_params, grid_scan_params, set_stub_offsets
    )
    yield from set_fast_grid_scan_params(fast_grid_scan, zebra_fgs_params)


def set_panda_fgs_params(
    panda_fast_grid_scan: PandAFastGridScan,
    expt_params: DiffractionExperiment,
    grid_scan_params: GridScanParams,
    *,
    run_up_distance_mm: float,
    set_stub_offsets: bool = False,
) -> MsgGenerator:
    panda_fgs_params = panda_fast_gridscan_params(
        expt_params, grid_scan_params, set_stub_offsets, run_up_distance_mm
    )
    yield from set_fast_grid_scan_params(panda_fast_grid_scan, panda_fgs_params)


def _fast_gridscan_3d_params(
    expt_params: DiffractionExperiment,
    grid_scan_params: GridScanParams,
    set_stub_offsets: bool,
) -> ZebraGridScanParamsThreeD:
    """During 3D grid scans, there is an omega rotation before the second grid,
    transforming Y -> Z axes, so use the second element of the Y params to set
    Z params on the 3D grid scan device.
    """
    return ZebraGridScanParamsThreeD(
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
        set_stub_offsets=set_stub_offsets,
        dwell_time_ms=expt_params.exposure_time_s * 1000,
        transmission_fraction=expt_params.transmission_frac,
    )


def panda_fast_gridscan_params(
    expt_params: DiffractionExperiment,
    grid_scan_params: GridScanParams,
    set_stub_offsets: bool,
    run_up_distance_mm: float,
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
        set_stub_offsets=set_stub_offsets,
        run_up_distance_mm=run_up_distance_mm,
        transmission_fraction=expt_params.transmission_frac,
    )


class OddYStepsError(Exception): ...
