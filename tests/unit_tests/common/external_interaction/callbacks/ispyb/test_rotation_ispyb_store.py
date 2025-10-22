import json
from unittest.mock import MagicMock, patch

import pytest

from mx_bluesky.common.external_interaction.ispyb.data_model import (
    DataCollectionInfo,
    DataCollectionPositionInfo,
    ScanDataInfo,
)
from mx_bluesky.common.external_interaction.ispyb.ispyb_store import (
    IspybIds,
    StoreInIspyb,
)

from ......conftest import (
    DC_COMMENT_RE,
    DC_RE,
    DCG_RE,
    DCGS_RE,
    DCS_RE,
    EXPECTED_END_TIME,
    EXPECTED_START_TIME,
    POSITION_RE,
    TEST_DATA_COLLECTION_GROUP_ID,
    TEST_DATA_COLLECTION_IDS,
    TEST_SAMPLE_ID,
)
from ...xray_centre.test_ispyb_handler import DCG_ID
from .test_gridscan_ispyb_store_3d import TEST_PROPOSAL_REF, TEST_VISIT_NUMBER

EXPECTED_UPDATE_DATA_COLLECTION = {
    "detectorId": 78,
    "axisStart": 0.0,
    "axisRange": 0.1,
    "axisEnd": 180,
    "beamSizeAtSampleX": 1,
    "beamSizeAtSampleY": 1,
    "transmission": 100.0,
    "dataCollectionNumber": 0,
    "detectorDistance": 100.0,
    "exposureTime": 0.1,
    "imageDirectory": "/tmp/",
    "imagePrefix": "file_name",
    "imageSuffix": "h5",
    "numberOfPasses": 1,
    "overlap": 0,
    "omegaStart": 0,
    "startImageNumber": 1,
    "wavelength": 123.98419840550369,
    "xBeam": 150.0,
    "yBeam": 160.0,
    "xtalSnapshotFullPath1": "test_1_y",
    "xtalSnapshotFullPath2": "test_2_y",
    "xtalSnapshotFullPath3": "test_3_y",
    "startTime": EXPECTED_START_TIME,
    "fileTemplate": "file_name_1_master.h5",
    "numberOfImages": 1800,
    "kappaStart": 0,
}

EXPECTED_BEGIN_DATA_COLLECTION = EXPECTED_UPDATE_DATA_COLLECTION | {
    "comments": "Hyperion rotation scan",
}


@pytest.fixture
@patch(
    "mx_bluesky.common.external_interaction.callbacks.common.ispyb_mapping.get_current_time_string",
    new=MagicMock(return_value=EXPECTED_START_TIME),
)
def scan_data_info_for_begin():
    return ScanDataInfo(
        data_collection_info=DataCollectionInfo(
            omega_start=0.0,
            data_collection_number=0,
            xtal_snapshot1="test_1_y",
            xtal_snapshot2="test_2_y",
            xtal_snapshot3="test_3_y",
            n_images=1800,
            axis_range=0.1,
            axis_end=180.0,
            kappa_start=0.0,
            parent_id=None,
            visit_string="cm31105-4",
            detector_id=78,
            axis_start=0.0,
            beamsize_at_samplex=1.0,
            beamsize_at_sampley=1.0,
            transmission=100.0,
            comments="Hyperion rotation scan",
            detector_distance=100.0,
            exp_time=0.1,
            imgdir="/tmp/",
            file_template="file_name_1_master.h5",
            imgprefix="file_name",
            imgsuffix="h5",
            n_passes=1,
            overlap=0,
            start_image_number=1,
            wavelength=123.98419840550369,
            xbeam=150.0,
            ybeam=160.0,
            synchrotron_mode=None,
            undulator_gap1=None,
            start_time="2024-02-08 14:03:59",
        ),
        data_collection_id=None,
        data_collection_position_info=None,
        data_collection_grid_info=None,
    )


@pytest.fixture
def scan_data_info_for_update(scan_data_info_for_begin):
    return ScanDataInfo(
        data_collection_info=DataCollectionInfo(
            omega_start=0.0,
            data_collection_number=0,
            xtal_snapshot1="test_1_y",
            xtal_snapshot2="test_2_y",
            xtal_snapshot3="test_3_y",
            n_images=1800,
            axis_range=0.1,
            axis_end=180.0,
            kappa_start=0.0,
            parent_id=None,
            visit_string="cm31105-4",
            detector_id=78,
            axis_start=0.0,
            slitgap_vertical=1.0,
            slitgap_horizontal=1.0,
            beamsize_at_samplex=1.0,
            beamsize_at_sampley=1.0,
            transmission=100.0,
            detector_distance=100.0,
            exp_time=0.1,
            imgdir="/tmp/",
            file_template="file_name_1_master.h5",
            imgprefix="file_name",
            imgsuffix="h5",
            n_passes=1,
            overlap=0,
            flux=10.0,
            start_image_number=1,
            wavelength=123.98419840550369,
            xbeam=150.0,
            ybeam=160.0,
            synchrotron_mode="test",
            undulator_gap1=None,
            start_time="2024-02-08 14:03:59",
        ),
        data_collection_position_info=DataCollectionPositionInfo(
            pos_x=10.0, pos_y=20.0, pos_z=30.0
        ),
        data_collection_grid_info=None,
    )


@patch(
    "mx_bluesky.common.external_interaction.callbacks.common.ispyb_mapping.get_current_time_string",
    new=MagicMock(return_value=EXPECTED_START_TIME),
)
def test_begin_deposition(
    mock_ispyb_conn,
    dummy_ispyb,
    dummy_rotation_data_collection_group_info,
    scan_data_info_for_begin,
):
    assert scan_data_info_for_begin.data_collection_info.parent_id is None

    assert dummy_ispyb.begin_deposition(
        dummy_rotation_data_collection_group_info, [scan_data_info_for_begin]
    ) == IspybIds(
        data_collection_ids=(TEST_DATA_COLLECTION_IDS[0],),
        data_collection_group_id=TEST_DATA_COLLECTION_GROUP_ID,
    )

    assert (
        scan_data_info_for_begin.data_collection_info.parent_id
        == TEST_DATA_COLLECTION_GROUP_ID
    )

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
    assert json.loads(create_dc_request.body) == EXPECTED_BEGIN_DATA_COLLECTION


@patch(
    "mx_bluesky.common.external_interaction.callbacks.common.ispyb_mapping.get_current_time_string",
    new=MagicMock(return_value=EXPECTED_START_TIME),
)
def test_begin_deposition_with_group_id_updates_but_doesnt_insert(
    mock_ispyb_conn,
    dummy_ispyb,
    dummy_rotation_data_collection_group_info,
    scan_data_info_for_begin,
):
    scan_data_info_for_begin.data_collection_info.parent_id = (
        TEST_DATA_COLLECTION_GROUP_ID
    )

    assert dummy_ispyb.begin_deposition(
        dummy_rotation_data_collection_group_info, [scan_data_info_for_begin]
    ) == IspybIds(
        data_collection_ids=(TEST_DATA_COLLECTION_IDS[0],),
        data_collection_group_id=TEST_DATA_COLLECTION_GROUP_ID,
    )
    assert len(mock_ispyb_conn.calls_for(DCGS_RE)) == 0
    update_dcg_request = mock_ispyb_conn.calls_for(DCG_RE)[0].request
    assert (
        int(mock_ispyb_conn.match(update_dcg_request, DCG_RE, 2))
        == TEST_DATA_COLLECTION_GROUP_ID
    )
    assert json.loads(update_dcg_request.body) == {
        "experimentType": "SAD",
        "sampleId": TEST_SAMPLE_ID,
    }
    create_dc_request = mock_ispyb_conn.calls_for(DCS_RE)[0].request
    assert (
        int(mock_ispyb_conn.match(create_dc_request, DCS_RE, 2))
        == TEST_DATA_COLLECTION_GROUP_ID
    )
    assert json.loads(create_dc_request.body) == EXPECTED_BEGIN_DATA_COLLECTION


@patch(
    "mx_bluesky.common.external_interaction.callbacks.common.ispyb_mapping.get_current_time_string",
    new=MagicMock(return_value=EXPECTED_START_TIME),
)
def test_begin_deposition_with_alternate_experiment_type(
    mock_ispyb_conn,
    dummy_ispyb,
    dummy_rotation_data_collection_group_info,
    scan_data_info_for_begin,
):
    dummy_rotation_data_collection_group_info.experiment_type = "Characterization"
    assert dummy_ispyb.begin_deposition(
        dummy_rotation_data_collection_group_info,
        [scan_data_info_for_begin],
    ) == IspybIds(
        data_collection_ids=(TEST_DATA_COLLECTION_IDS[0],),
        data_collection_group_id=TEST_DATA_COLLECTION_GROUP_ID,
    )
    create_dcg_request = mock_ispyb_conn.calls_for(DCGS_RE)[0].request
    assert mock_ispyb_conn.match(create_dcg_request, DCGS_RE, 2) == TEST_PROPOSAL_REF
    assert (
        int(mock_ispyb_conn.match(create_dcg_request, DCGS_RE, 3)) == TEST_VISIT_NUMBER
    )
    assert json.loads(create_dcg_request.body) == {
        "experimentType": "Characterization",
        "sampleId": TEST_SAMPLE_ID,
    }


@patch(
    "mx_bluesky.common.external_interaction.ispyb.ispyb_store.get_current_time_string",
    new=MagicMock(return_value=EXPECTED_START_TIME),
)
def test_update_deposition(
    mock_ispyb_conn,
    dummy_ispyb,
    dummy_rotation_data_collection_group_info,
    scan_data_info_for_begin,
    scan_data_info_for_update,
):
    ispyb_ids = dummy_ispyb.begin_deposition(
        dummy_rotation_data_collection_group_info, [scan_data_info_for_begin]
    )
    assert len(mock_ispyb_conn.calls_for(DCGS_RE)) == 1
    assert len(mock_ispyb_conn.calls_for(DCS_RE)) == 1
    assert len(mock_ispyb_conn.calls_for(DC_RE)) == 0

    scan_data_info_for_update.data_collection_info.parent_id = (
        ispyb_ids.data_collection_group_id
    )
    scan_data_info_for_update.data_collection_id = ispyb_ids.data_collection_ids[0]

    assert dummy_ispyb.update_deposition(
        ispyb_ids,
        [scan_data_info_for_update],
    ) == IspybIds(
        data_collection_group_id=TEST_DATA_COLLECTION_GROUP_ID,
        data_collection_ids=(TEST_DATA_COLLECTION_IDS[0],),
    )
    assert len(mock_ispyb_conn.calls_for(DCGS_RE)) == 1
    update_dc_request = mock_ispyb_conn.dc_calls_for(DC_RE)[0]
    assert update_dc_request.dcid == TEST_DATA_COLLECTION_IDS[0]
    assert update_dc_request.body == EXPECTED_UPDATE_DATA_COLLECTION | {
        "synchrotronMode": "test",
        "slitGapVertical": 1,
        "slitGapHorizontal": 1,
        "flux": 10,
    }

    create_pos_request = mock_ispyb_conn.dc_calls_for(POSITION_RE)[0]
    assert create_pos_request.dcid == TEST_DATA_COLLECTION_IDS[0]
    assert create_pos_request.body == {
        "posX": 10,
        "posY": 20,
        "posZ": 30,
    }


@patch(
    "mx_bluesky.common.external_interaction.callbacks.common.ispyb_mapping.get_current_time_string",
    new=MagicMock(return_value=EXPECTED_START_TIME),
)
def test_update_deposition_with_group_id_updates(
    mock_ispyb_conn,
    dummy_rotation_data_collection_group_info,
    scan_data_info_for_begin,
    scan_data_info_for_update,
    dummy_ispyb: StoreInIspyb,
):
    scan_data_info_for_begin.data_collection_info.parent_id = (
        TEST_DATA_COLLECTION_GROUP_ID
    )
    ispyb_ids = dummy_ispyb.begin_deposition(
        dummy_rotation_data_collection_group_info, [scan_data_info_for_begin]
    )
    assert len(mock_ispyb_conn.calls_for(DCGS_RE)) == 0
    assert len(mock_ispyb_conn.calls_for(DCS_RE)) == 1
    assert len(mock_ispyb_conn.calls_for(DC_RE)) == 0

    scan_data_info_for_update.data_collection_info.parent_id = (
        ispyb_ids.data_collection_group_id
    )
    scan_data_info_for_update.data_collection_id = ispyb_ids.data_collection_ids[0]

    assert dummy_ispyb.update_deposition(
        ispyb_ids,
        [scan_data_info_for_update],
    ) == IspybIds(
        data_collection_group_id=TEST_DATA_COLLECTION_GROUP_ID,
        data_collection_ids=(TEST_DATA_COLLECTION_IDS[0],),
    )
    assert len(mock_ispyb_conn.calls_for(DCGS_RE)) == 0
    assert len(mock_ispyb_conn.calls_for(DCG_ID)) == 0
    update_dc_request = mock_ispyb_conn.dc_calls_for(DC_RE)[0]
    assert update_dc_request.dcid == TEST_DATA_COLLECTION_IDS[0]
    assert update_dc_request.body == EXPECTED_UPDATE_DATA_COLLECTION | {
        "synchrotronMode": "test",
        "slitGapVertical": 1,
        "slitGapHorizontal": 1,
        "flux": 10,
    }

    update_position_request = mock_ispyb_conn.dc_calls_for(POSITION_RE)[0]
    assert update_position_request.dcid == TEST_DATA_COLLECTION_IDS[0]
    assert update_position_request.body == {
        "posX": 10,
        "posY": 20,
        "posZ": 30,
    }


@patch(
    "mx_bluesky.common.external_interaction.callbacks.common.ispyb_mapping.get_current_time_string",
    new=MagicMock(return_value=EXPECTED_START_TIME),
)
@patch(
    "mx_bluesky.common.external_interaction.ispyb.ispyb_store.get_current_time_string",
)
def test_end_deposition_happy_path(
    get_current_time,
    mock_ispyb_conn,
    dummy_ispyb,
    dummy_rotation_data_collection_group_info,
    scan_data_info_for_begin,
    scan_data_info_for_update,
):
    ispyb_ids = dummy_ispyb.begin_deposition(
        dummy_rotation_data_collection_group_info, [scan_data_info_for_begin]
    )
    scan_data_info_for_update.data_collection_info.parent_id = (
        ispyb_ids.data_collection_group_id
    )
    scan_data_info_for_update.data_collection_id = ispyb_ids.data_collection_ids[0]
    ispyb_ids = dummy_ispyb.update_deposition(
        ispyb_ids,
        [scan_data_info_for_update],
    )
    assert len(mock_ispyb_conn.calls_for(DC_RE)) == 1

    get_current_time.return_value = EXPECTED_END_TIME
    dummy_ispyb.end_deposition(ispyb_ids, "success", "Test succeeded")
    dcids_to_append_comment_reqs = {
        rq.dcid: rq for rq in mock_ispyb_conn.dc_calls_for(DC_COMMENT_RE)
    }
    assert dcids_to_append_comment_reqs[TEST_DATA_COLLECTION_IDS[0]].body == {
        "comments": " DataCollection Successful reason: Test succeeded",
    }
    assert len(mock_ispyb_conn.calls_for(DC_RE)) == 2
    update_dc_request = mock_ispyb_conn.dc_calls_for(DC_RE)[1]
    assert update_dc_request.dcid == TEST_DATA_COLLECTION_IDS[0]
    assert update_dc_request.body == {
        "endTime": EXPECTED_END_TIME,
        "runStatus": "DataCollection Successful",
    }


def test_store_rotation_scan_failures(mock_ispyb_conn, dummy_ispyb: StoreInIspyb):
    ispyb_ids = IspybIds(
        data_collection_group_id=TEST_DATA_COLLECTION_GROUP_ID,
    )
    with pytest.raises(AssertionError):
        dummy_ispyb.end_deposition(ispyb_ids, "", "")


@pytest.mark.parametrize(
    "mock_ispyb_conn, dcgid",
    [[{"dcg_id": dcg_id}, dcg_id] for dcg_id in [2, 45, 61, 88, 13, 25]],
    indirect=["mock_ispyb_conn"],
)
def test_store_rotation_scan_uses_supplied_dcgid(
    mock_ispyb_conn,
    dcgid,
    dummy_ispyb,
    dummy_rotation_data_collection_group_info,
    scan_data_info_for_begin,
    scan_data_info_for_update,
):
    scan_data_info_for_begin.data_collection_info.parent_id = dcgid
    ispyb_ids = dummy_ispyb.begin_deposition(
        dummy_rotation_data_collection_group_info, [scan_data_info_for_begin]
    )
    assert ispyb_ids.data_collection_group_id == dcgid
    update_dcg_request = mock_ispyb_conn.calls_for(DCG_RE)[0].request
    assert int(mock_ispyb_conn.match(update_dcg_request, DCG_RE, 2)) == dcgid
    assert json.loads(update_dcg_request.body) == {
        "experimentType": "SAD",
        "sampleId": TEST_SAMPLE_ID,
    }
    scan_data_info_for_update.data_collection_id = ispyb_ids.data_collection_ids[0]
    assert (
        dummy_ispyb.update_deposition(
            ispyb_ids,
            [scan_data_info_for_update],
        ).data_collection_group_id
        == dcgid
    )
