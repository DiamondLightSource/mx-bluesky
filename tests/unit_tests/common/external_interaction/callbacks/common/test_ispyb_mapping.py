import pytest
from event_model.documents import RunStart

from mx_bluesky.common.external_interaction.callbacks.common.ispyb_mapping import (
    populate_remaining_data_collection_info,
)
from mx_bluesky.common.external_interaction.ispyb.data_model import DataCollectionInfo
from mx_bluesky.common.parameters.constants import USE_NUMTRACKER
from mx_bluesky.common.parameters.gridscan import SpecifiedThreeDGridScan


def test_populate_remaining_data_collection_info_no_doc(
    test_fgs_params: SpecifiedThreeDGridScan,
):
    test_fgs_params.visit = USE_NUMTRACKER
    dc = DataCollectionInfo()
    with pytest.raises(AssertionError, match="Expected RunStart doc to be provided"):
        populate_remaining_data_collection_info("str", 10, dc, test_fgs_params)


def test_populate_remaining_data_collection_info_no_visit(
    test_fgs_params: SpecifiedThreeDGridScan,
):
    test_fgs_params.visit = USE_NUMTRACKER
    dc = DataCollectionInfo()
    doc = RunStart(uid="id", time=0)
    with pytest.raises(AssertionError, match="Failed to get instrument session "):
        populate_remaining_data_collection_info("str", 10, dc, test_fgs_params, doc)


def test_good_populate_remaining_data_collection_info(
    test_fgs_params: SpecifiedThreeDGridScan,
):
    test_fgs_params.visit = USE_NUMTRACKER
    doc = RunStart(uid="id", time=0)
    doc["instrument_session"] = "0"  # type: ignore
    dc = DataCollectionInfo()
    populate_remaining_data_collection_info("str", 10, dc, test_fgs_params, doc)
