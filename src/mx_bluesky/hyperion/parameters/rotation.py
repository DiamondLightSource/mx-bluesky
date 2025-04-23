from __future__ import annotations

import os
from collections.abc import Iterator
from itertools import accumulate
from typing import Annotated, Any, Self

from annotated_types import Len
from dodal.devices.aperturescatterguard import ApertureValue
from dodal.devices.detector import DetectorParams
from dodal.devices.zebra.zebra import (
    RotationDirection,
)
from dodal.log import LOGGER
from pydantic import Field, field_validator, model_validator
from scanspec.core import AxesPoints
from scanspec.core import Path as ScanPath
from scanspec.specs import Line

from mx_bluesky.common.parameters.components import (
    DiffractionExperimentWithSample,
    IspybExperimentType,
    OptionalGonioAngleStarts,
    OptionalXyzStarts,
    RotationAxis,
    SplitScan,
    WithScan,
)
from mx_bluesky.hyperion.parameters.components import WithHyperionUDCFeatures
from mx_bluesky.hyperion.parameters.constants import (
    CONST,
    I03Constants,
)


class RotationScanPerSweep(OptionalGonioAngleStarts, OptionalXyzStarts):
    """
    Describes a rotation scan about the specified axis.

    Attributes:
        rotation_axis: The rotation axis, by default this is the omega axis
        omega_start_deg: The initial angle of the rotation in degrees (default 0)
        scan_width_deg: The sweep of the rotation in degrees, this must be positive (default 360)
        rotation_direction: Indicates the direction of rotation, if RotationDirection.POSITIVE
            the final angle is obtained by adding scan_width_deg, otherwise by subtraction (default NEGATIVE)
        nexus_vds_start_img: The frame number of the first frame captured during the rotation
    """

    omega_start_deg: float = Field(default=0)  # type: ignore
    rotation_axis: RotationAxis = Field(default=RotationAxis.OMEGA)
    scan_width_deg: float = Field(default=360, gt=0)
    rotation_direction: RotationDirection = Field(default=RotationDirection.NEGATIVE)
    nexus_vds_start_img: int = Field(default=0, ge=0)


class RotationExperiment(DiffractionExperimentWithSample, WithHyperionUDCFeatures):
    shutter_opening_time_s: float = Field(default=CONST.I03.SHUTTER_TIME_S)
    rotation_increment_deg: float = Field(default=0.1, gt=0)
    ispyb_experiment_type: IspybExperimentType = Field(
        default=IspybExperimentType.ROTATION
    )

    def _detector_params_impl(
        self, omega_start_deg: float, num_images_per_trigger: int, num_triggers: int
    ) -> DetectorParams:
        self.det_dist_to_beam_converter_path = (
            self.det_dist_to_beam_converter_path
            or CONST.PARAM.DETECTOR.BEAM_XY_LUT_PATH
        )
        optional_args = {}
        if self.run_number:
            optional_args["run_number"] = self.run_number
        assert self.detector_distance_mm is not None
        os.makedirs(self.storage_directory, exist_ok=True)
        return DetectorParams(
            detector_size_constants=I03Constants.DETECTOR,
            expected_energy_ev=self.demand_energy_ev,
            exposure_time_s=self.exposure_time_s,
            directory=self.storage_directory,
            prefix=self.file_name,
            detector_distance=self.detector_distance_mm,
            omega_start=omega_start_deg,
            omega_increment=self.rotation_increment_deg,
            num_images_per_trigger=num_images_per_trigger,
            num_triggers=num_triggers,
            use_roi_mode=False,
            det_dist_to_beam_converter_path=self.det_dist_to_beam_converter_path,
            **optional_args,
        )

    def _detector_params(self, omega_start_deg: float) -> DetectorParams:
        return self._detector_params_impl(omega_start_deg, self.num_images, 1)

    @field_validator("selected_aperture")
    @classmethod
    def _set_default_aperture_position(cls, aperture_position: ApertureValue | None):
        if not aperture_position:
            default_aperture = CONST.PARAM.ROTATION.DEFAULT_APERTURE_POSITION
            LOGGER.warning(
                f"No aperture position selected. Defaulting to {default_aperture}"
            )
            return default_aperture
        else:
            return aperture_position


class RotationScan(WithScan, RotationScanPerSweep, RotationExperiment):
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


class MultiRotationScan(RotationExperiment, SplitScan):
    rotation_scans: Annotated[list[RotationScanPerSweep], Len(min_length=1)]

    def _single_rotation_scan(self, scan: RotationScanPerSweep) -> RotationScan:
        # self has everything from RotationExperiment
        allowed_keys = RotationScan.model_fields.keys()  # type: ignore # mypy doesn't recognise this as a property...
        params_dump = self.model_dump()
        # provided `scan` has everything from RotationScanPerSweep
        scan_dump = scan.model_dump()
        rotation_scan_kv_pairs = {
            k: v for k, v in (params_dump | scan_dump).items() if k in allowed_keys
        }
        # together they have everything for RotationScan
        rotation_scan = RotationScan(**rotation_scan_kv_pairs)
        return rotation_scan

    @model_validator(mode="after")
    @classmethod
    def correct_start_vds(cls, values: Any) -> Any:
        assert isinstance(values, MultiRotationScan)
        start_img = 0.0
        for scan in values.rotation_scans:
            scan.nexus_vds_start_img = int(start_img)
            start_img += scan.scan_width_deg / values.rotation_increment_deg
        return values

    @model_validator(mode="after")
    def _check_valid_for_single_arm_multiple_sweep(self) -> Self:
        if len(self.rotation_scans) > 0:
            scan_width = self.rotation_scans[0].scan_width_deg
            for scan in self.rotation_scans[1:]:
                assert scan.scan_width_deg == scan_width, (
                    "Sweeps with different numbers of frames are not supported."
                )

        return self

    @property
    def single_rotation_scans(self) -> Iterator[RotationScan]:
        for scan in self.rotation_scans:
            yield self._single_rotation_scan(scan)

    def _num_images_per_scan(self):
        return [
            int(scan.scan_width_deg / self.rotation_increment_deg)
            for scan in self.rotation_scans
        ]

    @property
    def num_images(self):
        return sum(self._num_images_per_scan())

    @property
    def scan_indices(self):
        return list(accumulate([0, *self._num_images_per_scan()]))

    @property
    def detector_params(self) -> DetectorParams:
        return self._detector_params_impl(
            self.rotation_scans[0].omega_start_deg,
            self._num_images_per_scan()[0],
            len(self._num_images_per_scan()),
        )
