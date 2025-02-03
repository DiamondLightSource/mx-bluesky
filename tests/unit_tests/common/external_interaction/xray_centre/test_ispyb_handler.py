from unittest.mock import MagicMock, patch

from mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback import (
    GridscanISPyBCallback,
)
from mx_bluesky.common.external_interaction.ispyb.ispyb_store import (
    IspybIds,
    StoreInIspyb,
)
from mx_bluesky.common.parameters.gridscan import SpecifiedThreeDGridScan

from .....conftest import TestData

DC_IDS = (1, 2)
DCG_ID = 4
DC_GRID_IDS = (11, 12)
td = TestData()


def mock_store_in_ispyb(config, *args, **kwargs) -> StoreInIspyb:
    mock = MagicMock(spec=StoreInIspyb)
    mock.end_deposition = MagicMock(return_value=None)
    mock.begin_deposition = MagicMock(
        return_value=IspybIds(
            data_collection_group_id=DCG_ID, data_collection_ids=DC_IDS
        )
    )
    mock.update_deposition = MagicMock(
        return_value=IspybIds(
            data_collection_group_id=DCG_ID,
            data_collection_ids=DC_IDS,
            grid_ids=DC_GRID_IDS,
        )
    )
    mock.append_to_comment = MagicMock()
    return mock


@patch(
    "mx_bluesky.common.external_interaction.callbacks.common.ispyb_mapping.get_current_time_string",
    MagicMock(return_value=td.DUMMY_TIME_STRING),
)
@patch(
    "mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback.StoreInIspyb",
    mock_store_in_ispyb,
)
class TestXrayCentreIspybHandler:
    def test_fgs_failing_results_in_bad_run_status_in_ispyb(
        self,
    ):
        ispyb_handler = GridscanISPyBCallback(param_type=SpecifiedThreeDGridScan)
        ispyb_handler.activity_gated_start(td.test_gridscan3d_start_document)
        ispyb_handler.activity_gated_descriptor(
            td.test_descriptor_document_pre_data_collection
        )
        ispyb_handler.activity_gated_event(td.test_event_document_pre_data_collection)
        ispyb_handler.activity_gated_descriptor(
            td.test_descriptor_document_during_data_collection
        )
        ispyb_handler.activity_gated_event(
            td.test_event_document_during_data_collection  # pyright: ignore
        )
        ispyb_handler.activity_gated_stop(td.test_run_gridscan_failed_stop_document)

        ispyb_handler.ispyb.end_deposition.assert_called_once_with(  # type: ignore
            IspybIds(
                data_collection_group_id=DCG_ID,
                data_collection_ids=DC_IDS,
                grid_ids=DC_GRID_IDS,
            ),
            "fail",
            "could not connect to devices",
        )

    def test_fgs_raising_no_exception_results_in_good_run_status_in_ispyb(
        self,
    ):
        ispyb_handler = GridscanISPyBCallback(param_type=SpecifiedThreeDGridScan)
        ispyb_handler.activity_gated_start(td.test_gridscan3d_start_document)
        ispyb_handler.activity_gated_descriptor(
            td.test_descriptor_document_pre_data_collection
        )
        ispyb_handler.activity_gated_event(td.test_event_document_pre_data_collection)
        ispyb_handler.activity_gated_descriptor(
            td.test_descriptor_document_during_data_collection
        )
        ispyb_handler.activity_gated_event(
            td.test_event_document_during_data_collection
        )
        ispyb_handler.activity_gated_stop(td.test_do_fgs_gridscan_stop_document)

        ispyb_handler.ispyb.end_deposition.assert_called_once_with(  # type: ignore
            IspybIds(
                data_collection_group_id=DCG_ID,
                data_collection_ids=DC_IDS,
                grid_ids=DC_GRID_IDS,
            ),
            "success",
            "",
        )

    @patch(
        "mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback.time",
        side_effect=[2, 100],
    )
    def test_given_fgs_plan_finished_when_zocalo_results_event_then_expected_comment_deposited(
        self, mock_time
    ):
        ispyb_handler = GridscanISPyBCallback(param_type=SpecifiedThreeDGridScan)

        ispyb_handler.activity_gated_start(td.test_gridscan3d_start_document)  # type:ignore

        ispyb_handler.activity_gated_start(td.test_do_fgs_start_document)  # type:ignore
        ispyb_handler.activity_gated_stop(td.test_do_fgs_gridscan_stop_document)

        ispyb_handler.activity_gated_descriptor(
            td.test_descriptor_document_zocalo_reading
        )
        ispyb_handler.activity_gated_event(td.test_zocalo_reading_event)

        assert (
            ispyb_handler.ispyb.append_to_comment.call_args.args[1]  # type:ignore
            == "Zocalo processing took 98.00 s. Zocalo found no crystals in this gridscan."
        )
