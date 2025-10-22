from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from pydantic import BaseModel

from mx_bluesky.common.external_interaction.callbacks.common.ispyb_mapping import (
    get_proposal_and_session_from_visit_string,
)
from mx_bluesky.common.external_interaction.ispyb.data_model import (
    DataCollectionGroupInfo,
    DataCollectionInfo,
    ScanDataInfo,
)
from mx_bluesky.common.external_interaction.ispyb.exp_eye_store import ExpeyeInteraction
from mx_bluesky.common.external_interaction.ispyb.ispyb_utils import (
    get_current_time_string,
)
from mx_bluesky.common.utils.exceptions import ISPyBDepositionNotMade
from mx_bluesky.common.utils.log import ISPYB_ZOCALO_CALLBACK_LOGGER

if TYPE_CHECKING:
    pass


class IspybIds(BaseModel):
    data_collection_ids: tuple[int, ...] = ()
    data_collection_group_id: int | None = None
    grid_ids: tuple[int, ...] = ()


class StoreInIspyb:
    def __init__(self, ispyb_config: str) -> None:
        self.ISPYB_CONFIG_PATH: str = ispyb_config
        self._expeye = ExpeyeInteraction()

    def begin_deposition(
        self,
        data_collection_group_info: DataCollectionGroupInfo,
        scan_data_infos: Sequence[ScanDataInfo],
    ) -> IspybIds:
        ispyb_ids = IspybIds()
        if scan_data_infos[0].data_collection_info:
            ispyb_ids.data_collection_group_id = scan_data_infos[
                0
            ].data_collection_info.parent_id

        return self._begin_or_update_deposition(
            ispyb_ids, data_collection_group_info, scan_data_infos
        )

    def update_deposition(
        self,
        ispyb_ids,
        scan_data_infos: Sequence[ScanDataInfo],
    ) -> IspybIds:
        assert ispyb_ids.data_collection_group_id, (
            "Attempted to store scan data without a collection group"
        )
        assert ispyb_ids.data_collection_ids, (
            "Attempted to store scan data without a collection"
        )
        return self._begin_or_update_deposition(ispyb_ids, None, scan_data_infos)

    def _begin_or_update_deposition(
        self,
        ispyb_ids,
        data_collection_group_info: DataCollectionGroupInfo | None,
        scan_data_infos,
    ) -> IspybIds:
        if data_collection_group_info:
            ispyb_ids.data_collection_group_id = (
                self._store_data_collection_group_table(
                    data_collection_group_info, ispyb_ids.data_collection_group_id
                )
            )
        else:
            assert ispyb_ids.data_collection_group_id, (
                "Attempt to update data collection without a data collection group ID"
            )

        grid_ids = list(ispyb_ids.grid_ids)
        data_collection_ids_out = list(ispyb_ids.data_collection_ids)
        for scan_data_info in scan_data_infos:
            data_collection_id = scan_data_info.data_collection_id
            if (
                scan_data_info.data_collection_info
                and not scan_data_info.data_collection_info.parent_id
            ):
                scan_data_info.data_collection_info.parent_id = (
                    ispyb_ids.data_collection_group_id
                )

            new_data_collection_id, grid_id = self._store_single_scan_data(
                scan_data_info, data_collection_id
            )
            if not data_collection_id:
                data_collection_ids_out.append(new_data_collection_id)
            if grid_id:
                grid_ids.append(grid_id)
        ispyb_ids = IspybIds(
            data_collection_ids=tuple(data_collection_ids_out),
            grid_ids=tuple(grid_ids),
            data_collection_group_id=ispyb_ids.data_collection_group_id,
        )
        return ispyb_ids

    def end_deposition(self, ispyb_ids: IspybIds, success: str, reason: str):
        assert ispyb_ids.data_collection_ids, (
            "Can't end ISPyB deposition, data_collection IDs are missing"
        )
        assert ispyb_ids.data_collection_group_id is not None, (
            "Cannot end ISPyB deposition without data collection group ID"
        )

        for id_ in ispyb_ids.data_collection_ids:
            ISPYB_ZOCALO_CALLBACK_LOGGER.info(
                f"End ispyb deposition with status '{success}' and reason '{reason}'."
            )
            if success == "fail" or success == "abort":
                run_status = "DataCollection Unsuccessful"
            else:
                run_status = "DataCollection Successful"
            current_time = get_current_time_string()
            self._update_scan_with_end_time_and_status(
                current_time, run_status, reason, id_
            )

    def append_to_comment(
        self, data_collection_id: int, comment: str, delimiter: str = " "
    ) -> None:
        try:
            self._expeye.update_data_collection(
                data_collection_id,
                DataCollectionInfo(comments=delimiter + comment),
                True,
            )
        except ISPyBDepositionNotMade as e:
            ISPYB_ZOCALO_CALLBACK_LOGGER.warning(
                f"Unable to log comment, comment probably exceeded column length: {comment}",
                exc_info=e,
            )

    def update_data_collection_group_table(
        self,
        dcg_info: DataCollectionGroupInfo,
        data_collection_group_id: int | None = None,
    ) -> None:
        self._store_data_collection_group_table(dcg_info, data_collection_group_id)

    def _update_scan_with_end_time_and_status(
        self, end_time: str, run_status: str, reason: str, data_collection_id: int
    ) -> None:
        if reason is not None and reason != "":
            self.append_to_comment(data_collection_id, f"{run_status} reason: {reason}")

        info = DataCollectionInfo(end_time=end_time, run_status=run_status)
        self._expeye.update_data_collection(data_collection_id, info)

    def _store_data_collection_group_table(
        self,
        dcg_info: DataCollectionGroupInfo,
        data_collection_group_id: int | None = None,
    ) -> int:
        if data_collection_group_id:
            self._expeye.update_data_group(data_collection_group_id, dcg_info)
            return data_collection_group_id
        else:
            proposal, session = get_proposal_and_session_from_visit_string(
                dcg_info.visit_string
            )
            return self._expeye.create_data_group(proposal, session, dcg_info)

    def _store_data_collection_table(
        self, data_collection_id, data_collection_info: DataCollectionInfo
    ) -> int:
        if data_collection_id and data_collection_info.comments:
            self.append_to_comment(
                data_collection_id, data_collection_info.comments, " "
            )
            data_collection_info.comments = None

        if data_collection_id:
            self._expeye.update_data_collection(
                data_collection_id, data_collection_info
            )
            return data_collection_id
        else:
            assert data_collection_info.parent_id, (
                "Data Collection must have a Data Collection Group"
            )
            return self._expeye.create_data_collection(
                data_collection_info.parent_id, data_collection_info
            )

    def _store_single_scan_data(
        self, scan_data_info, data_collection_id=None
    ) -> tuple[int, int | None]:
        data_collection_id = self._store_data_collection_table(
            data_collection_id, scan_data_info.data_collection_info
        )

        if scan_data_info.data_collection_position_info:
            self._expeye.create_position(
                data_collection_id, scan_data_info.data_collection_position_info
            )

        grid_id = None
        if scan_data_info.data_collection_grid_info:
            grid_id = self._expeye.create_grid(
                data_collection_id, scan_data_info.data_collection_grid_info
            )
        return data_collection_id, grid_id
