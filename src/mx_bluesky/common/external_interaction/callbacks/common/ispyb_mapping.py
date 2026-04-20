from __future__ import annotations

from mx_bluesky.common.external_interaction.ispyb.data_model import (
    DataCollectionGroupInfo,
    DataCollectionInfo,
)
from mx_bluesky.common.external_interaction.ispyb.ispyb_store import (
    EIGER_FILE_SUFFIX,
    I03_EIGER_DETECTOR,
)
from mx_bluesky.common.external_interaction.ispyb.ispyb_utils import (
    get_current_time_string,
)
from mx_bluesky.common.parameters.components import DiffractionExperimentWithSample


def populate_data_collection_group(params: DiffractionExperimentWithSample):
    dcg_info = DataCollectionGroupInfo(
        visit_string=params.visit,
        experiment_type=params.ispyb_experiment_type.value,
        sample_id=params.sample_id,
    )
    return dcg_info


def populate_remaining_data_collection_info(
    comment,
    data_collection_group_id,
    data_collection_info: DataCollectionInfo,
    params: DiffractionExperimentWithSample,
):
    data_collection_info.visit_string = params.visit
    data_collection_info.parent_id = data_collection_group_id
    data_collection_info.sample_id = params.sample_id
    data_collection_info.detector_id = I03_EIGER_DETECTOR
    data_collection_info.comments = comment
    data_collection_info.detector_distance = params.detector_params.detector_distance
    data_collection_info.exp_time = params.detector_params.exposure_time_s
    data_collection_info.imgdir = params.detector_params.directory
    data_collection_info.imgprefix = params.detector_params.prefix
    data_collection_info.imgsuffix = EIGER_FILE_SUFFIX
    # Both overlap and n_passes included for backwards compatibility,
    # planned to be removed later
    data_collection_info.n_passes = 1
    data_collection_info.overlap = 0
    data_collection_info.start_image_number = 1
    beam_position = params.detector_params.get_beam_position_mm(
        params.detector_params.detector_distance
    )
    data_collection_info.xbeam = beam_position[0]
    data_collection_info.ybeam = beam_position[1]
    data_collection_info.start_time = get_current_time_string()
    # temporary file template until nxs filewriting is integrated and we can use
    # that file name
    data_collection_info.file_template = f"{params.detector_params.prefix}_{data_collection_info.data_collection_number}_master.h5"
    return data_collection_info


def get_proposal_and_session_from_visit_string(visit_string: str) -> tuple[str, int]:
    visit_parts = visit_string.split("-")
    assert len(visit_parts) == 2, f"Unexpected visit string {visit_string}"
    return visit_parts[0], int(visit_parts[1])
