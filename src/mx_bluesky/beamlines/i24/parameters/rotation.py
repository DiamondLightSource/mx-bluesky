from __future__ import annotations

from scanspec.core import AxesPoints
from scanspec.core import Path as ScanPath
from scanspec.specs import Line

from mx_bluesky.common.parameters.components import (
    DiffractionExperimentWithSample,
    WithScan,
)
from mx_bluesky.common.parameters.rotation import (
    RotationExperiment,
    RotationScanPerSweep,
)


class InternalRotationScanParams(
    WithScan, RotationScanPerSweep, RotationExperiment, DiffractionExperimentWithSample
):
    @property
    def detector_params(self):
        return self._detector_params(self.omega_start_deg)

    @property
    def scan_points(self) -> AxesPoints:
        """The scan points are defined in application space"""
        scan_spec = Line(
            axis="omega",
            start=self.omega_start_deg,
            stop=(
                self.omega_start_deg
                + (self.scan_width_deg - self.rotation_increment_deg)
            ),
            num=self.num_images,
        )
        scan_path = ScanPath(scan_spec.calculate())
        return scan_path.consume().midpoints

    @property
    def num_images(self) -> int:
        return int(self.scan_width_deg / self.rotation_increment_deg)
