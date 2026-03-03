from dodal.devices.beamlines.i02_1.fast_grid_scan import ZebraGridScanParamsTwoD
from pydantic import model_validator

from mx_bluesky.common.parameters.components import SplitScan, WithOptionalEnergyChange
from mx_bluesky.common.parameters.gridscan import SpecifiedGrids


class SpecifiedTwoDGridScan(
    SpecifiedGrids[ZebraGridScanParamsTwoD],
    SplitScan,
    WithOptionalEnergyChange,
):
    """Parameters representing a so-called 2D grid scan, which consists of doing a
    gridscan in X and Y."""

    @property
    def fast_gridscan_params(self) -> ZebraGridScanParamsTwoD:
        return ZebraGridScanParamsTwoD(
            x_steps=self.x_steps,
            y_steps=self.y_steps[0],
            x_step_size_mm=self.x_step_size_um / 1000,
            y_step_size_mm=self.y_step_sizes_um[0] / 1000,
            x_start_mm=self.x_start_um / 1000,
            y1_start_mm=self.y_starts_um[0] / 1000,
            z1_start_mm=self.z_starts_um[0] / 1000,
            set_stub_offsets=self._set_stub_offsets,
            transmission_fraction=0.5,
            dwell_time_ms=self.exposure_time_s * 1000,
        )

    @model_validator(mode="after")
    def validate_y_axes(self):
        _err_str = "must be length 1 for 2D scans"
        if len(self.y_steps) != 1:
            raise ValueError(f"{self.y_steps=} {_err_str}")
        if len(self.y_step_sizes_um) != 1:
            raise ValueError(f"{self.y_step_sizes_um=} {_err_str}")
        if len(self.omega_starts_deg) != 1:
            raise ValueError(f"{self.omega_starts_deg=} {_err_str}")

        return self
