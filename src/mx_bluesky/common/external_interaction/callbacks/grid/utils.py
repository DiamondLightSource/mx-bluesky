from __future__ import annotations

from time import time

from dodal.devices.zocalo import ZocaloStartInfo

from mx_bluesky.common.external_interaction.callbacks.common.ispyb_callback_base import (
    BaseISPyBCallback,
)
from mx_bluesky.common.external_interaction.callbacks.common.zocalo_callback import (
    ZocaloInfoGenerator,
)
from mx_bluesky.common.external_interaction.ispyb.data_model import (
    DataCollectionGroupInfo,
    DataCollectionInfo,
)
from mx_bluesky.common.parameters.constants import PlanNameConstants
from mx_bluesky.common.parameters.gridscan import SpecifiedGrids
from mx_bluesky.common.utils.utils import number_of_frames_from_scan_spec

ASSERT_START_BEFORE_EVENT_DOC_MESSAGE = f"No data collection group info - event document has been emitted before a {PlanNameConstants.GRID_DETECT_AND_DO_GRIDSCAN} start document"


def generate_start_info_from_omega_map(
    omega_positions: list[int],
) -> ZocaloInfoGenerator:
    """
    Generate the zocalo trigger info from bluesky runs where the frame number is
    computed using metadata added to the document by the ISPyB callback and the
    run start which together can be used to determine the correct frame numbering.
    """
    doc = yield []
    omega_to_scan_spec = doc["omega_to_scan_spec"]
    start_frame = 0
    infos = []
    omegas_str = [str(omega) for omega in omega_positions]
    for i, omega in enumerate(omegas_str):
        frames = number_of_frames_from_scan_spec(omega_to_scan_spec[omega])
        infos.append(
            ZocaloStartInfo(
                doc["grid_plane_to_id_map"][omega], None, start_frame, frames, i
            )
        )
        start_frame += frames
    yield infos


def generate_start_info_from_num_grids(
    params: SpecifiedGrids,
) -> ZocaloInfoGenerator:
    """
    Generate the zocalo trigger info from bluesky runs where the grid specs
    are immediately known from entry parameters. Metadata added to the document
    by the ispyb callback maps the data collection id to the grid number.
    """

    doc = yield []
    start_frame = 0
    infos = []
    for grid_num in range(params.num_grids):
        frames = len(params.scan_points[grid_num])
        infos.append(
            ZocaloStartInfo(
                doc["_grid_num_to_id_map"][grid_num],
                None,
                start_frame,
                frames,
                grid_num,
            )
        )
        start_frame += frames
    yield infos


def common_populate_axis_info(data_collection_info: DataCollectionInfo, doc: dict):
    if (omega_start := doc.get("gonio-omega")) is not None:
        omega_in_gda_space = -omega_start
        data_collection_info.omega_start = omega_in_gda_space
        data_collection_info.axis_start = omega_in_gda_space
        data_collection_info.axis_end = omega_in_gda_space
        data_collection_info.axis_range = 0
    if (chi_start := doc.get("gonio-chi")) is not None:
        data_collection_info.chi_start = chi_start


def add_processing_time_to_comment(
    callback: BaseISPyBCallback,
    processing_start_time: float,
    data_collection_group_info: DataCollectionGroupInfo | None,
):
    assert data_collection_group_info, ASSERT_START_BEFORE_EVENT_DOC_MESSAGE
    proc_time = time() - processing_start_time
    crystal_summary = f"Zocalo processing took {proc_time:.2f} s."

    data_collection_group_info.comments = (
        data_collection_group_info.comments or ""
    ) + crystal_summary

    callback.ispyb.append_to_comment(
        callback.ispyb_ids.data_collection_ids[0], crystal_summary
    )
