from dodal.devices.i02_1.fast_grid_scan import ZebraGridScanParamsTwoD
from scanspec.specs import Product

from mx_bluesky.common.parameters.components import SplitScan, WithOptionalEnergyChange
from mx_bluesky.common.parameters.gridscan import SpecifiedGrid


class SpecifiedTwoDGridScan(
    SpecifiedGrid[ZebraGridScanParamsTwoD],
    SplitScan,
    WithOptionalEnergyChange,
):
    """Parameters representing a so-called 2D grid scan, which consists of doing a
    gridscan in X and Y."""

    @property
    def scan_spec(self) -> Product[str]:
        """A fully specified ScanSpec object representing the grid, with x, y, z and
        omega positions."""
        return self.grid_1_spec

    @property
    def fast_gridscan_params(self) -> ZebraGridScanParamsTwoD:
        return ZebraGridScanParamsTwoD(
            x_steps=self.x_steps,
            y_steps=self.y_steps,
            x_step_size_mm=self.x_step_size_um / 1000,
            y_step_size_mm=self.y_step_size_um / 1000,
            x_start_mm=self.x_start_um / 1000,
            y1_start_mm=self.y_start_um / 1000,
            z1_start_mm=self.z_start_um / 1000,
            set_stub_offsets=self._set_stub_offsets,
            transmission_fraction=0.5,
            dwell_time_ms=self.exposure_time_s,
        )
