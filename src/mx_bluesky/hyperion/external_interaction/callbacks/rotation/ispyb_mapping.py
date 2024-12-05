from __future__ import annotations

from mx_bluesky.common.external_interaction.ispyb.data_model import DataCollectionInfo
from mx_bluesky.hyperion.parameters.rotation import RotationScan


def populate_data_collection_info_for_rotation(params: RotationScan):
    info = DataCollectionInfo(
        omega_start=params.omega_start_deg,
        data_collection_number=params.detector_params.run_number,  # type:ignore # the validator always makes this int
        n_images=params.num_images,
        axis_range=params.rotation_increment_deg,
        axis_start=params.omega_start_deg,
        axis_end=(params.omega_start_deg + params.scan_width_deg),
        kappa_start=params.kappa_start_deg,
    )
    return info
