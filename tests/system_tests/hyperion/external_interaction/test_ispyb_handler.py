from unittest.mock import MagicMock, patch

import pytest
from graypy import GELFTCPHandler

from mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback import (
    GridscanISPyBCallback,
)
from mx_bluesky.common.parameters.gridscan import SpecifiedThreeDGridScan
from mx_bluesky.common.utils.log import ISPYB_ZOCALO_CALLBACK_LOGGER
from mx_bluesky.hyperion.external_interaction.callbacks.__main__ import setup_logging
from tests.unit_tests.common.external_interaction.xray_centre.test_ispyb_handler import (
    mock_store_in_ispyb,
)

from ....conftest import TestData

DC_IDS = (1, 2)
DCG_ID = 4
DC_GRID_IDS = (11, 12)
td = TestData()


@patch(
    "mx_bluesky.common.external_interaction.callbacks.common.ispyb_mapping.get_current_time_string",
    MagicMock(return_value=td.DUMMY_TIME_STRING),
)
@patch(
    "mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback.StoreInIspyb",
    mock_store_in_ispyb,
)
class TestXrayCentreIspybHandler:
    @pytest.mark.skip_log_setup
    def test_given_ispyb_callback_started_writing_to_ispyb_when_messages_logged_then_they_contain_dcgid(
        self,
    ):
        setup_logging(True)
        gelf_handler: MagicMock = next(
            filter(
                lambda h: isinstance(h, GELFTCPHandler),
                ISPYB_ZOCALO_CALLBACK_LOGGER.handlers,  # type: ignore
            )
        )
        gelf_handler.emit = MagicMock()

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

        ISPYB_ZOCALO_CALLBACK_LOGGER.info("test")
        latest_record = gelf_handler.emit.call_args.args[-1]
        assert latest_record.dc_group_id == DCG_ID

    @pytest.mark.skip_log_setup
    def test_given_ispyb_callback_finished_writing_to_ispyb_when_messages_logged_then_they_do_not_contain_dcgid(
        self,
    ):
        setup_logging(True)
        gelf_handler: MagicMock = next(
            filter(
                lambda h: isinstance(h, GELFTCPHandler),
                ISPYB_ZOCALO_CALLBACK_LOGGER.handlers,  # type: ignore
            )
        )
        gelf_handler.emit = MagicMock()

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
        ispyb_handler.activity_gated_stop(td.test_run_gridscan_failed_stop_document)

        ISPYB_ZOCALO_CALLBACK_LOGGER.info("test")
        latest_record = gelf_handler.emit.call_args.args[-1]
        assert not hasattr(latest_record, "dc_group_id")
