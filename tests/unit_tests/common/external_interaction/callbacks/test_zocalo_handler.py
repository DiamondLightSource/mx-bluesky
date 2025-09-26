from unittest.mock import MagicMock, call, patch

import pytest
from dodal.devices.zocalo import ZocaloStartInfo

from mx_bluesky.common.external_interaction.callbacks.common.zocalo_callback import (
    ZocaloCallback,
    ZocaloTrigger,
)
from mx_bluesky.common.external_interaction.ispyb.ispyb_store import (
    IspybIds,
    StoreInIspyb,
)
from mx_bluesky.common.utils.exceptions import ISPyBDepositionNotMade
from mx_bluesky.hyperion.external_interaction.callbacks.__main__ import (
    create_gridscan_callbacks,
)
from mx_bluesky.hyperion.external_interaction.callbacks.rotation.ispyb_callback import (
    generate_start_info_from_ordered_runs,
)

EXPECTED_RUN_START_MESSAGE = {"subplan_name": "test_plan_name", "uid": "my_uuid"}
EXPECTED_RUN_END_MESSAGE = {"event": "end", "run_start": "my_uuid"}


class TestZocaloHandler:
    def _setup_handler(self):
        zocalo_handler = ZocaloCallback(
            "test_plan_name", "test_env", generate_start_info_from_ordered_runs
        )
        return zocalo_handler

    def test_handler_doesnt_trigger_on_wrong_plan(self):
        zocalo_handler = self._setup_handler()
        zocalo_handler.start({"sybplan_name": "_not_test_plan_name"})  # type: ignore
        assert len(zocalo_handler.zocalo_info) == 0

    @patch(
        "mx_bluesky.common.external_interaction.callbacks.common.zocalo_callback.ZocaloTrigger",
        autospec=True,
    )
    def test_handler_stores_collection_if_ispyb_ids_come_in_with_triggering_plan(
        self, zocalo_trigger: ZocaloTrigger
    ):
        zocalo_handler = self._setup_handler()
        assert not zocalo_handler.zocalo_info
        zocalo_handler.start(
            {
                **EXPECTED_RUN_START_MESSAGE,
                "ispyb_dcids": (135, 139),
                "scan_points": [{"test": [1, 2, 3]}, {"test": [2, 3, 4]}],
            }  # type: ignore
        )
        assert len(zocalo_handler.zocalo_info) == 2

    @patch(
        "mx_bluesky.common.external_interaction.callbacks.common.zocalo_callback.ZocaloTrigger",
        autospec=True,
    )
    def test_handler_stores_collection_ispyb_ids_come_in_as_subplan(
        self, zocalo_trigger: ZocaloTrigger
    ):
        zocalo_handler = self._setup_handler()
        assert not zocalo_handler.zocalo_info
        zocalo_handler.start(EXPECTED_RUN_START_MESSAGE)  # type: ignore
        assert not zocalo_handler.zocalo_info
        zocalo_handler.start(
            {
                "subplan_name": "other_plan",
                "ispyb_dcids": (135,),
                "scan_points": [{"test": [1, 2, 3]}],
            }  # type: ignore
        )
        zocalo_handler.start(
            {
                "subplan_name": "other_plan",
                "ispyb_dcids": (563,),
                "scan_points": [{"test": [2, 3, 4]}],
            }  # type: ignore
        )

        assert len(zocalo_handler.zocalo_info) == 2

    @patch(
        "mx_bluesky.common.external_interaction.callbacks.common.zocalo_callback.ZocaloTrigger",
        autospec=True,
    )
    @patch(
        "mx_bluesky.common.external_interaction.callbacks.xray_centre.nexus_callback.NexusWriter",
    )
    @patch(
        "mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback.StoreInIspyb",
    )
    def test_execution_of_do_fgs_triggers_zocalo_calls(
        self,
        ispyb_store: MagicMock,
        nexus_writer: MagicMock,
        zocalo_trigger,
        TestEventData,
    ):
        dc_ids = (1, 2)
        dcg_id = 4

        mock_ids = IspybIds(data_collection_ids=dc_ids, data_collection_group_id=dcg_id)
        ispyb_store.return_value.mock_add_spec(StoreInIspyb)

        _, ispyb_cb = create_gridscan_callbacks()
        ispyb_cb.active = True
        assert isinstance(zocalo_handler := ispyb_cb.emit_cb, ZocaloCallback)
        zocalo_handler._reset_state()
        zocalo_handler._reset_state = MagicMock()

        ispyb_store.return_value.begin_deposition.return_value = mock_ids
        ispyb_store.return_value.update_deposition.return_value = mock_ids

        ispyb_cb.start(TestEventData.test_grid_detect_and_gridscan_start_document)  # type: ignore
        ispyb_cb.descriptor(TestEventData.test_descriptor_document_oav_snapshot)
        ispyb_cb.event(TestEventData.test_event_document_oav_snapshot_xy)
        ispyb_cb.event(TestEventData.test_event_document_oav_snapshot_xz)
        ispyb_cb.start(TestEventData.test_gridscan_outer_start_document)  # type: ignore
        ispyb_cb.start(TestEventData.test_do_fgs_start_document)  # type: ignore
        ispyb_cb.descriptor(TestEventData.test_descriptor_document_pre_data_collection)  # type: ignore
        ispyb_cb.event(TestEventData.test_event_document_pre_data_collection)
        ispyb_cb.descriptor(TestEventData.test_descriptor_document_zocalo_hardware)
        ispyb_cb.event(TestEventData.test_event_document_zocalo_hardware)
        ispyb_cb.descriptor(
            TestEventData.test_descriptor_document_during_data_collection  # type: ignore
        )
        ispyb_cb.event(TestEventData.test_event_document_during_data_collection)
        assert zocalo_handler.zocalo_interactor is not None

        expected_start_calls = [
            call(ZocaloStartInfo(1, "test_path", 0, 200, 0)),
            call(ZocaloStartInfo(2, "test_path", 200, 300, 1)),
        ]

        zocalo_handler.zocalo_interactor.run_start.assert_has_calls(  # type: ignore
            expected_start_calls
        )
        assert zocalo_handler.zocalo_interactor.run_start.call_count == len(dc_ids)  # type: ignore

        ispyb_cb.stop(TestEventData.test_do_fgs_stop_document)
        ispyb_cb.stop(TestEventData.test_gridscan_outer_stop_document)

        zocalo_handler.zocalo_interactor.run_end.assert_has_calls(  # type: ignore
            [call(x) for x in dc_ids]
        )
        assert zocalo_handler.zocalo_interactor.run_end.call_count == len(dc_ids)  # type: ignore

        zocalo_handler._reset_state.assert_called()

    @patch(
        "mx_bluesky.common.external_interaction.callbacks.common.zocalo_callback.ZocaloTrigger",
        autospec=True,
    )
    @patch(
        "mx_bluesky.common.external_interaction.callbacks.xray_centre.nexus_callback.NexusWriter",
    )
    @patch(
        "mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback.StoreInIspyb",
    )
    def test_do_fgs_triggers_zocalo_calls_when_snapshots_in_reverse_order(
        self,
        ispyb_store: MagicMock,
        nexus_writer: MagicMock,
        zocalo_trigger,
        TestEventData,
    ):
        dc_ids = (1, 2)
        dcg_id = 4

        mock_ids = IspybIds(data_collection_ids=dc_ids, data_collection_group_id=dcg_id)
        ispyb_store.return_value.mock_add_spec(StoreInIspyb)

        _, ispyb_cb = create_gridscan_callbacks()
        ispyb_cb.active = True
        assert isinstance(zocalo_handler := ispyb_cb.emit_cb, ZocaloCallback)
        zocalo_handler._reset_state()
        zocalo_handler._reset_state = MagicMock()

        ispyb_store.return_value.begin_deposition.return_value = mock_ids
        ispyb_store.return_value.update_deposition.return_value = mock_ids

        ispyb_cb.start(TestEventData.test_grid_detect_and_gridscan_start_document)  # type: ignore
        ispyb_cb.start(TestEventData.test_gridscan_outer_start_document)  # type: ignore
        ispyb_cb.descriptor(TestEventData.test_descriptor_document_oav_snapshot)
        ispyb_cb.event(TestEventData.test_event_document_oav_snapshot_xz)
        ispyb_cb.event(TestEventData.test_event_document_oav_snapshot_xy)
        ispyb_cb.start(TestEventData.test_do_fgs_start_document)  # type: ignore
        ispyb_cb.descriptor(TestEventData.test_descriptor_document_pre_data_collection)  # type: ignore
        ispyb_cb.event(TestEventData.test_event_document_pre_data_collection)
        ispyb_cb.descriptor(TestEventData.test_descriptor_document_zocalo_hardware)
        ispyb_cb.event(TestEventData.test_event_document_zocalo_hardware)
        ispyb_cb.descriptor(
            TestEventData.test_descriptor_document_during_data_collection  # type: ignore
        )
        ispyb_cb.event(TestEventData.test_event_document_during_data_collection)
        assert zocalo_handler.zocalo_interactor is not None

        expected_start_calls = [
            call(ZocaloStartInfo(2, "test_path", 0, 200, 0)),
            call(ZocaloStartInfo(1, "test_path", 200, 300, 1)),
        ]

        zocalo_handler.zocalo_interactor.run_start.assert_has_calls(  # type: ignore
            expected_start_calls
        )
        assert zocalo_handler.zocalo_interactor.run_start.call_count == len(dc_ids)  # type: ignore
        ispyb_cb.stop(TestEventData.test_do_fgs_stop_document)
        ispyb_cb.stop(TestEventData.test_gridscan_outer_stop_document)

        zocalo_handler.zocalo_interactor.run_end.assert_has_calls(  # type: ignore
            [call(dc_ids[1]), call(dc_ids[0])]
        )
        assert zocalo_handler.zocalo_interactor.run_end.call_count == len(dc_ids)  # type: ignore

    @patch(
        "mx_bluesky.common.external_interaction.callbacks.common.zocalo_callback.ZocaloTrigger",
        autospec=True,
    )
    def test_handler_raises_on_the_end_of_a_plan_with_no_depositions(
        self, zocalo_trigger: ZocaloTrigger
    ):
        zocalo_handler = self._setup_handler()
        zocalo_handler.start(EXPECTED_RUN_START_MESSAGE)  # type: ignore
        with pytest.raises(ISPyBDepositionNotMade):
            zocalo_handler.stop(EXPECTED_RUN_END_MESSAGE)  # type: ignore
