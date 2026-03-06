from collections.abc import Sequence
from unittest.mock import MagicMock, patch

import pytest
from event_model import RunStop

from mx_bluesky.common.external_interaction.callbacks.grid.gridscan.ispyb_callback import (
    GridscanISPyBCallback,
)
from mx_bluesky.common.external_interaction.ispyb.data_model import (
    DataCollectionGroupInfo,
    DataCollectionInfo,
    ScanDataInfo,
)
from mx_bluesky.common.external_interaction.ispyb.ispyb_store import (
    IspybIds,
    StoreInIspyb,
)
from mx_bluesky.common.parameters.constants import PlanNameConstants
from mx_bluesky.common.parameters.gridscan import (
    SpecifiedThreeDGridScan,
)
from mx_bluesky.common.utils.exceptions import ISPyBDepositionNotMadeError


class Callback(GridscanISPyBCallback):
    def _get_scan_infos(self, doc) -> Sequence[ScanDataInfo]:
        return [ScanDataInfo(data_collection_info=DataCollectionInfo())]


@patch(
    "mx_bluesky.common.external_interaction.callbacks.grid.gridscan.ispyb_callback.BaseISPyBCallback.activity_gated_start"
)
def test_gridscan_callback_start_calls_correct_funcs(
    mock_start: MagicMock, test_three_d_grid_params: SpecifiedThreeDGridScan
):
    cb = Callback(SpecifiedThreeDGridScan)
    cb.fill_gridscan_deposition_and_store = MagicMock()
    doc = {
        "subplan_name": PlanNameConstants.TRIGGER_GRIDSCAN_ISPYB_CALLBACK,
        "mx_bluesky_parameters": test_three_d_grid_params.model_dump_json(),
    }
    cb.activity_gated_start(doc)  # type: ignore
    cb.fill_gridscan_deposition_and_store.assert_called_once()
    mock_start.assert_called_once()


def test_populate_info_for_update(test_three_d_grid_params: SpecifiedThreeDGridScan):
    cb = Callback(SpecifiedThreeDGridScan)
    cb.params = test_three_d_grid_params
    cb.ispyb_ids = IspybIds(data_collection_ids=(0, 1))
    cb._grid_num_to_id_map = {0: 0, 1: 1}
    es_dcid = DataCollectionInfo()
    infos = cb.populate_info_for_update(es_dcid, None, test_three_d_grid_params)
    assert infos == [
        ScanDataInfo(data_collection_id=0, data_collection_info=DataCollectionInfo()),
        ScanDataInfo(data_collection_id=1, data_collection_info=DataCollectionInfo()),
    ]


def test_stop_errors_if_empty_ispyb_id():
    cb = Callback(SpecifiedThreeDGridScan)
    cb.ispyb_ids = IspybIds()
    cb.data_collection_group_info = DataCollectionGroupInfo("", "", None)
    doc: RunStop = {
        "time": 0,
        "uid": "0",
        "exit_status": "success",
        "run_start": None,  # type: ignore
    }
    with pytest.raises(ISPyBDepositionNotMadeError):
        cb.activity_gated_stop(doc)


def test_exception_added_onto_comments():
    cb = Callback(SpecifiedThreeDGridScan)
    cb.ispyb = StoreInIspyb("")
    cb.ispyb.update_data_collection_group_table = MagicMock()
    cb.ispyb_ids = IspybIds(data_collection_ids=(0,))
    cb.data_collection_group_info = DataCollectionGroupInfo("", "", None)
    reason = "test reason"
    doc: RunStop = {
        "time": 0,
        "uid": "0",
        "exit_status": "success",
        "run_start": None,  # type: ignore
        "reason": f"[test]: {reason}",
    }
    cb.activity_gated_stop(doc)
    cb.ispyb.update_data_collection_group_table.assert_called_once_with(
        DataCollectionGroupInfo("", "", None, comments=reason), None
    )


@patch(
    "mx_bluesky.common.external_interaction.callbacks.grid.gridscan.ispyb_callback.StoreInIspyb"
)
def test_fill_gridscan_deposition_and_store(
    mock_store: MagicMock,
    test_three_d_grid_params: SpecifiedThreeDGridScan,
):
    cb = Callback(SpecifiedThreeDGridScan)
    cb.params = test_three_d_grid_params
    ispyb = StoreInIspyb("")
    ispyb.begin_deposition = MagicMock()
    ispyb.update_deposition = MagicMock()
    ispyb.update_data_collection_group_table = MagicMock()
    mock_store.return_value = ispyb
    cb.fill_gridscan_deposition_and_store(MagicMock())
    ispyb.begin_deposition.assert_called_once()
    ispyb.update_deposition.assert_called_once()
    ispyb.update_data_collection_group_table.assert_called_once()
