from dodal.devices.beamlines.i02_1.fast_grid_scan import ZebraGridScanParamsTwoD

from mx_bluesky.common.parameters.components import DiffractionExperiment
from mx_bluesky.common.parameters.gridscan import GridScanParams


def fast_gridscan_params(
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
