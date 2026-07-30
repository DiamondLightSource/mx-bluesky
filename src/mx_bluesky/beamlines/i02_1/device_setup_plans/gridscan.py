from __future__ import annotations

from bluesky.utils import MsgGenerator
from dodal.devices.beamlines.i02_1.fast_grid_scan import ZebraGridScanParamsTwoD
from dodal.devices.fast_grid_scan import FastGridScanCommon, set_fast_grid_scan_params

from mx_bluesky.common.parameters.components import DiffractionExperiment
from mx_bluesky.common.parameters.gridscan import GridScanParams


def set_zebra_fgs_2d_params(
    fast_grid_scan: FastGridScanCommon[ZebraGridScanParamsTwoD],
    expt_params: DiffractionExperiment,
    grid_scan_params: GridScanParams,
) -> MsgGenerator:
    zebra_fgs_params = _fast_gridscan_2d_params(expt_params, grid_scan_params)
    yield from set_fast_grid_scan_params(fast_grid_scan, zebra_fgs_params)


def _fast_gridscan_2d_params(
    params: DiffractionExperiment, grid_scan_params: GridScanParams
) -> ZebraGridScanParamsTwoD:
    return ZebraGridScanParamsTwoD(
        x_steps=grid_scan_params.x_steps,
        y_steps=grid_scan_params.y_steps[0],
        x_step_size_mm=grid_scan_params.x_step_size_um / 1000,
        y_step_size_mm=grid_scan_params.y_step_sizes_um[0] / 1000,
        x_start_mm=grid_scan_params.x_start_um / 1000,
        y1_start_mm=grid_scan_params.y_starts_um[0] / 1000,
        z1_start_mm=grid_scan_params.z_starts_um[0] / 1000,
        set_stub_offsets=False,
        transmission_fraction=0.5,
        dwell_time_ms=params.exposure_time_s * 1000,
    )
