"""
Define beamline parameters for I03, Eiger detector and give an example of writing a
gridscan.
"""

from __future__ import annotations

import math
from pathlib import Path

from dodal.utils import get_beamline_name
from nexgen.nxs_utils import Attenuator, Beam, Detector, Goniometer, Source
from nexgen.nxs_write.nxmx_writer import NXmxFileWriter
from numpy.typing import DTypeLike
from scanspec.core import AxesPoints

from mx_bluesky.common.external_interaction.nexus.nexus_utils import (
    AxisDirection,
    create_detector_parameters,
    create_goniometer_axes,
    get_start_and_predicted_end_time,
)
from mx_bluesky.common.parameters.components import DiffractionExperiment


class NexusWriter:
    def __init__(
        self,
        parameters: DiffractionExperiment,
        data_shape: tuple[int, int, int],
        scan_points: AxesPoints,
        *,
        run_number: int | None = None,
        omega_start_deg: float = 0,
        chi_start_deg: float = 0,
        phi_start_deg: float = 0,
        vds_start_index: int = 0,
        # override default values when there is more than one collection per
        # detector arming event:
        full_num_of_images: int | None = None,
        meta_data_run_number: int | None = None,
        axis_direction: AxisDirection = AxisDirection.NEGATIVE,
    ) -> None:
        self.beam: Beam | None = None
        self.attenuator: Attenuator | None = None
        self.scan_points: dict = scan_points
        self.data_shape: tuple[int, int, int] = data_shape
        self.run_number: int = (
            run_number if run_number else parameters.detector_params.run_number
        )
        self.detector: Detector = create_detector_parameters(parameters.detector_params)
        self.source: Source = Source(get_beamline_name("S03"))
        self.directory: Path = Path(parameters.storage_directory)
        self.start_index: int = vds_start_index
        self.full_num_of_images: int = full_num_of_images or parameters.num_images
        self.data_filename: str = (
            f"{parameters.file_name}_{meta_data_run_number}"
            if meta_data_run_number
            else parameters.detector_params.full_filename
        )
        self.nexus_file: Path = (
            self.directory / f"{parameters.file_name}_{self.run_number}.nxs"
        )
        self.master_file: Path = (
            self.directory / f"{parameters.file_name}_{self.run_number}_master.h5"
        )
        self.goniometer: Goniometer = create_goniometer_axes(
            omega_start_deg,
            self.scan_points,
            chi=chi_start_deg,
            phi=phi_start_deg,
            omega_axis_direction=axis_direction,
        )

    def create_nexus_file(self, bit_depth: DTypeLike):
        """
        Creates a nexus file based on the parameters supplied when this object was
        initialised.
        """
        start_time, est_end_time = get_start_and_predicted_end_time(
            self.detector.exp_time * self.full_num_of_images
        )

        assert self.beam is not None
        assert self.attenuator is not None

        vds_shape = self.data_shape

        for filename in [self.nexus_file, self.master_file]:
            NXmx_Writer = NXmxFileWriter(
                filename,
                self.goniometer,
                self.detector,
                self.source,
                self.beam,
                self.attenuator,
                self.full_num_of_images,
            )
            NXmx_Writer.write(
                image_filename=f"{self.data_filename}",
                start_time=start_time,
                est_end_time=est_end_time,
            )
            NXmx_Writer.write_vds(
                vds_offset=self.start_index, vds_shape=vds_shape, vds_dtype=bit_depth
            )

    def get_image_datafiles(self, max_images_per_file=1000):
        return [
            self.directory / f"{self.data_filename}_{h5_num + 1:06}.h5"
            for h5_num in range(
                math.ceil(self.full_num_of_images / max_images_per_file)
            )
        ]
