import json
from unittest.mock import MagicMock, patch

from mx_bluesky.hyperion.external_interaction.callbacks.rotation.ispyb_callback import (
    RotationISPyBCallback,
)

from ......conftest import (
    EXPECTED_END_TIME,
    EXPECTED_START_TIME,
    replace_all_tmp_paths,
)
from ......expeye_helpers import (
    DC_COMMENT_RE,
    DC_RE,
    DCG_RE,
    DCGS_RE,
    DCS_RE,
    POSITION_RE,
    TEST_DATA_COLLECTION_GROUP_ID,
    TEST_DATA_COLLECTION_IDS,
)
from .....common.external_interaction.callbacks.ispyb.test_gridscan_ispyb_store_3d import (
    TEST_PROPOSAL_REF,
    TEST_VISIT_NUMBER,
)

TEST_SAMPLE_ID = 123456

EXPECTED_DATA_COLLECTION = {
    "detectorId": 78,
    "axisStart": 0.0,
    "axisRange": 0.1,
    "axisEnd": -180,
    "comments": "test",
    "chiStart": 23.85,
    "dataCollectionNumber": 1,
    "detectorDistance": 100.0,
    "exposureTime": 0.1,
    "imageDirectory": "{tmp_data}/123456/",
    "imagePrefix": "file_name",
    "imageSuffix": "h5",
    "numberOfPasses": 1,
    "overlap": 0,
    "omegaStart": 0,
    "startImageNumber": 1,
    "xBeam": 150.0,
    "yBeam": 160.0,
    "startTime": EXPECTED_START_TIME,
    "fileTemplate": "file_name_1_master.h5",
    "numberOfImages": 1800,
}


@patch(
    "mx_bluesky.common.external_interaction.callbacks.common.ispyb_mapping.get_current_time_string",
    new=MagicMock(return_value=EXPECTED_START_TIME),
)
def test_activity_gated_start(
    mock_ispyb_conn, test_rotation_start_outer_document, tmp_path
):
    callback = RotationISPyBCallback()

    callback.activity_gated_start(test_rotation_start_outer_document)
    create_dcg_request = mock_ispyb_conn.calls_for(DCGS_RE)[0].request
    assert mock_ispyb_conn.match(create_dcg_request, DCGS_RE, 2) == TEST_PROPOSAL_REF
    assert (
        int(mock_ispyb_conn.match(create_dcg_request, DCGS_RE, 3)) == TEST_VISIT_NUMBER
    )
    assert json.loads(create_dcg_request.body) == {
        "experimentType": "SAD",
        "sampleId": TEST_SAMPLE_ID,
    }
    create_dc_request = mock_ispyb_conn.calls_for(DCS_RE)[0].request
    assert (
        int(mock_ispyb_conn.match(create_dc_request, DCS_RE, 2))
        == TEST_DATA_COLLECTION_GROUP_ID
    )
    assert json.loads(create_dc_request.body) == replace_all_tmp_paths(
        EXPECTED_DATA_COLLECTION, tmp_path
    )


@patch(
    "mx_bluesky.common.external_interaction.callbacks.common.ispyb_mapping.get_current_time_string",
    new=MagicMock(return_value=EXPECTED_START_TIME),
)
def test_hardware_read_events(
    mock_ispyb_conn, test_rotation_start_outer_document, test_event_data
):
    callback = RotationISPyBCallback()
    callback.activity_gated_start(test_rotation_start_outer_document)  # pyright: ignore
    callback.activity_gated_start(
        test_event_data.test_rotation_start_main_document  # pyright: ignore
    )

    callback.activity_gated_descriptor(
        test_event_data.test_descriptor_document_pre_data_collection
    )
    callback.activity_gated_event(
        test_event_data.test_event_document_pre_data_collection
    )
    assert len(mock_ispyb_conn.calls_for(DCG_RE)) == 0
    update_dc_request = mock_ispyb_conn.dc_calls_for(DC_RE)[0]
    assert update_dc_request.dcid == TEST_DATA_COLLECTION_IDS[0]
    assert update_dc_request.body == {
        "slitGapHorizontal": 0.1234,
        "slitGapVertical": 0.2345,
        "synchrotronMode": "User",
        "undulatorGap1": 1.234,
        "resolution": 1.1830593331191241,
        "wavelength": 1.11647184541378,
    }
    append_comments_req = list(mock_ispyb_conn.dc_calls_for(DC_COMMENT_RE))[0]
    assert append_comments_req.dcid == TEST_DATA_COLLECTION_IDS[0]
    assert append_comments_req.body == {
        "comments": " Sample position (µm): (158, 24, 3)"
    }

    expected_data = test_event_data.test_event_document_pre_data_collection["data"]
    create_position_request = mock_ispyb_conn.dc_calls_for(POSITION_RE)[0]
    assert create_position_request.dcid == TEST_DATA_COLLECTION_IDS[0]
    assert create_position_request.body == {
        "posX": expected_data["smargon-x"],
        "posY": expected_data["smargon-y"],
        "posZ": expected_data["smargon-z"],
    }


@patch(
    "mx_bluesky.common.external_interaction.callbacks.common.ispyb_mapping.get_current_time_string",
    new=MagicMock(return_value=EXPECTED_START_TIME),
)
def test_flux_read_events(
    mock_ispyb_conn, test_rotation_start_outer_document, test_event_data
):
    callback = RotationISPyBCallback()
    callback.activity_gated_start(test_rotation_start_outer_document)  # pyright: ignore
    callback.activity_gated_start(
        test_event_data.test_rotation_start_main_document  # pyright: ignore
    )
    callback.activity_gated_descriptor(
        test_event_data.test_descriptor_document_pre_data_collection
    )
    callback.activity_gated_event(
        test_event_data.test_event_document_pre_data_collection
    )
    assert len(mock_ispyb_conn.calls_for(DC_RE)) == 1
    callback.activity_gated_descriptor(
        test_event_data.test_descriptor_document_during_data_collection
    )
    callback.activity_gated_event(
        test_event_data.test_rotation_event_document_during_data_collection
    )

    assert len(mock_ispyb_conn.calls_for(DCG_RE)) == 0
    update_dc_request = mock_ispyb_conn.dc_calls_for(DC_RE)[1]
    assert update_dc_request.dcid == TEST_DATA_COLLECTION_IDS[0]
    assert update_dc_request.body == {
        "beamSizeAtSampleX": 0.05,
        "beamSizeAtSampleY": 0.02,
        "wavelength": 1.11647184541378,
        "transmission": 98,
        "flux": 9.81,
        "resolution": 1.1830593331191241,
    }


@patch(
    "mx_bluesky.common.external_interaction.callbacks.common.ispyb_mapping.get_current_time_string",
    new=MagicMock(return_value=EXPECTED_START_TIME),
)
def test_oav_rotation_snapshot_triggered_event(
    mock_ispyb_conn, test_rotation_start_outer_document, test_event_data
):
    callback = RotationISPyBCallback()
    callback.activity_gated_start(test_rotation_start_outer_document)  # pyright: ignore
    callback.activity_gated_start(
        test_event_data.test_rotation_start_main_document  # pyright: ignore
    )
    callback.activity_gated_descriptor(
        test_event_data.test_descriptor_document_oav_rotation_snapshot
    )

    assert len(mock_ispyb_conn.calls_for(DC_RE)) == 0
    i = 0
    for snapshot in [
        {"filename": "snapshot_0", "colname": "xtalSnapshotFullPath1"},
        {"filename": "snapshot_90", "colname": "xtalSnapshotFullPath2"},
        {"filename": "snapshot_180", "colname": "xtalSnapshotFullPath3"},
        {"filename": "snapshot_270", "colname": "xtalSnapshotFullPath4"},
    ]:
        event_doc = dict(test_event_data.test_event_document_oav_rotation_snapshot)
        event_doc["data"]["oav-snapshot-last_saved_path"] = snapshot["filename"]  # type: ignore
        callback.activity_gated_event(event_doc)  # type: ignore
        update_dc_request = mock_ispyb_conn.dc_calls_for(DC_RE)[i]
        assert update_dc_request.dcid == TEST_DATA_COLLECTION_IDS[0]
        assert update_dc_request.body == {
            snapshot["colname"]: snapshot["filename"],
        }
        i += 1

    assert len(mock_ispyb_conn.calls_for(DCG_RE)) == 0


@patch(
    "mx_bluesky.common.external_interaction.callbacks.common.ispyb_mapping.get_current_time_string",
    new=MagicMock(return_value=EXPECTED_START_TIME),
)
def test_activity_gated_stop(
    mock_ispyb_conn,
    test_rotation_start_outer_document,
    test_rotation_stop_outer_document,
    test_event_data,
):
    callback = RotationISPyBCallback()
    callback.activity_gated_start(test_rotation_start_outer_document)  # pyright: ignore
    callback.activity_gated_start(
        test_event_data.test_rotation_start_main_document  # pyright: ignore
    )

    assert len(mock_ispyb_conn.calls_for(DCG_RE)) == 0
    assert len(mock_ispyb_conn.calls_for(DC_RE)) == 0

    with patch(
        "mx_bluesky.common.external_interaction.ispyb.ispyb_store.get_current_time_string",
        new=MagicMock(return_value=EXPECTED_END_TIME),
    ):
        callback.activity_gated_stop(test_event_data.test_rotation_stop_main_document)
        callback.activity_gated_stop(test_rotation_stop_outer_document)

    update_comment_req = mock_ispyb_conn.dc_calls_for(DC_COMMENT_RE)[0]
    assert update_comment_req.dcid == TEST_DATA_COLLECTION_IDS[0]
    assert update_comment_req.body == {
        "comments": " DataCollection Successful reason: Test succeeded"
    }
    update_dc_request = mock_ispyb_conn.dc_calls_for(DC_RE)[0]
    assert update_dc_request.dcid == TEST_DATA_COLLECTION_IDS[0]
    assert update_dc_request.body == {
        "endTime": EXPECTED_END_TIME,
        "runStatus": "DataCollection Successful",
    }
    assert len(mock_ispyb_conn.dc_calls_for(DC_RE)) == 1


def test_comment_correct_after_hardware_read(
    mock_ispyb_conn, test_rotation_start_outer_document, test_event_data
):
    callback = RotationISPyBCallback()
    test_rotation_start_outer_document["mx_bluesky_parameters"] = (
        test_rotation_start_outer_document["mx_bluesky_parameters"].replace(
            '"comment":"test"', '"comment":"a lovely unit test"'
        )
    )
    callback.activity_gated_start(test_rotation_start_outer_document)  # pyright: ignore
    callback.activity_gated_start(
        test_event_data.test_rotation_start_main_document  # pyright: ignore
    )

    create_dc_request = mock_ispyb_conn.dc_calls_for(DCS_RE)[0]
    assert create_dc_request.body["comments"] == "a lovely unit test"

    callback.activity_gated_descriptor(
        test_event_data.test_descriptor_document_pre_data_collection
    )
    callback.activity_gated_event(
        test_event_data.test_event_document_pre_data_collection
    )
    update_dc_request = mock_ispyb_conn.dc_calls_for(DC_RE)[0]
    assert update_dc_request.dcid == TEST_DATA_COLLECTION_IDS[0]
    assert update_dc_request.body == {
        "slitGapHorizontal": 0.1234,
        "slitGapVertical": 0.2345,
        "synchrotronMode": "User",
        "undulatorGap1": 1.234,
        "resolution": 1.1830593331191241,
        "wavelength": 1.11647184541378,
    }
    update_dc_comment_req = mock_ispyb_conn.dc_calls_for(DC_COMMENT_RE)[0]
    assert update_dc_comment_req.dcid == TEST_DATA_COLLECTION_IDS[0]
    assert update_dc_comment_req.body == {
        "comments": " Sample position (µm): (158, 24, 3)"
    }
