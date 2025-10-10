import json
from dataclasses import replace
from unittest.mock import MagicMock, patch

import pytest
from ispyb import ReadWriteError

from mx_bluesky.common.external_interaction.ispyb.data_model import (
    DataCollectionGridInfo,
    DataCollectionGroupInfo,
    DataCollectionInfo,
    DataCollectionPositionInfo,
    Orientation,
    ScanDataInfo,
)
from mx_bluesky.common.external_interaction.ispyb.ispyb_store import (
    IspybIds,
    StoreInIspyb,
)

from ......conftest import (
    DC_RE,
    DCG_RE,
    DCGS_RE,
    DCS_RE,
    EXPECTED_END_TIME,
    EXPECTED_START_TIME,
    GRID_RE,
    POSITION_RE,
    TEST_BARCODE,
    TEST_DATA_COLLECTION_GROUP_ID,
    TEST_DATA_COLLECTION_IDS,
    TEST_GRID_INFO_IDS,
    TEST_SAMPLE_ID,
    mx_acquisition_from_conn,
)

TEST_PROPOSAL_REF = "cm31105"
TEST_VISIT_NUMBER = 4


@pytest.fixture
def dummy_collection_group_info():
    return DataCollectionGroupInfo(
        visit_string="cm31105-4",
        experiment_type="Mesh3D",
        sample_id=364758,
    )


DC_INFO_FOR_BEGIN_XY = DataCollectionInfo(
    omega_start=0.0,
    data_collection_number=1,
    xtal_snapshot1="test_1_y",
    xtal_snapshot2="test_2_y",
    xtal_snapshot3="test_3_y",
    n_images=800,
    axis_range=0,
    axis_end=0.0,
    kappa_start=None,
    parent_id=None,
    visit_string="cm31105-4",
    sample_id=364758,
    detector_id=78,
    axis_start=0.0,
    focal_spot_size_at_samplex=0.0,
    focal_spot_size_at_sampley=0.0,
    slitgap_vertical=0.1,
    slitgap_horizontal=0.1,
    beamsize_at_samplex=0.1,
    beamsize_at_sampley=0.1,
    transmission=100.0,
    comments="MX-Bluesky: Xray centring 1 -",
    detector_distance=100.0,
    exp_time=0.1,
    imgdir="/tmp/",
    file_template="file_name_0_master.h5",
    imgprefix="file_name",
    imgsuffix="h5",
    n_passes=1,
    overlap=0,
    start_image_number=1,
    wavelength=123.98419840550369,
    xbeam=150.0,
    ybeam=160.0,
    synchrotron_mode=None,
    undulator_gap1=1.0,
    start_time=EXPECTED_START_TIME,
)

DC_INFO_FOR_BEGIN_XZ = replace(
    DC_INFO_FOR_BEGIN_XY,
    xtal_snapshot1="test_1_z",
    xtal_snapshot2="test_2_z",
    xtal_snapshot3="test_3_z",
    omega_start=90.0,
    n_images=400,
    axis_end=90.0,
    axis_start=90.0,
    file_template="file_name_1_master.h5",
    comments="MX-Bluesky: Xray centring 2 -",
)

DC_INFO_FOR_UPDATE_XY = replace(
    DC_INFO_FOR_BEGIN_XY,
    parent_id=34,
    comments="Diffraction grid scan of 40 by 20 images in 100.0 um by 100.0 um steps. Top left (px): [50,100], bottom right (px): [3250,1700].",
    flux=10.0,
    synchrotron_mode="test",
)

DC_INFO_FOR_UPDATE_XZ = replace(
    DC_INFO_FOR_BEGIN_XZ,
    parent_id=34,
    comments="Diffraction grid scan of 40 by 10 images in 100.0 um by 200.0 um steps. Top left (px): [50,120], bottom right (px): [3250,1720].",
    flux=10.0,
    synchrotron_mode="test",
)

EXPECTED_BASE_UPSERT = {
    "detectorId": 78,
    "axisRange": 0,
    # "focalSpotSizeAtSampleX": 0.0, TODO
    # "focalSpotSizeAtSampleY": 0.0, TODO
    "slitGapVertical": 0.1,
    "slitGapHorizontal": 0.1,
    "beamSizeAtSampleX": 0.1,
    "beamSizeAtSampleY": 0.1,
    "transmission": 100.0,
    # "dataCollectionNumber": 1, TODO
    "detectorDistance": 100.0,
    "exposureTime": 0.1,
    "imageDirectory": "/tmp/",
    "imagePrefix": "file_name",
    "imageSuffix": "h5",
    "numberOfPasses": 1,
    "overlap": 0,
    "startImageNumber": 1,
    "wavelength": 123.98419840550369,
    "xBeam": 150.0,
    "yBeam": 160.0,
    "undulatorGap1": 1.0,
    "startTime": EXPECTED_START_TIME,
}

EXPECTED_BASE_XY_UPSERT = EXPECTED_BASE_UPSERT | {
    "xtalSnapshotFullPath1": "test_1_y",
    "xtalSnapshotFullPath2": "test_2_y",
    "xtalSnapshotFullPath3": "test_3_y",
    "omegaStart": 0,
    "axisStart": 0.0,
    "axisEnd": 0,
    "fileTemplate": "file_name_0_master.h5",
    "numberOfImages": 40 * 20,
}

EXPECTED_BASE_XZ_UPSERT = EXPECTED_BASE_UPSERT | {
    "xtalSnapshotFullPath1": "test_1_z",
    "xtalSnapshotFullPath2": "test_2_z",
    "xtalSnapshotFullPath3": "test_3_z",
    "omegaStart": 90.0,
    "axisStart": 90.0,
    "axisEnd": 90.0,
    "fileTemplate": "file_name_1_master.h5",
    "numberOfImages": 40 * 10,
}

EXPECTED_DC_XY_BEGIN_UPSERT = EXPECTED_BASE_XY_UPSERT | {
    "comments": "MX-Bluesky: Xray centring 1 -",
}

EXPECTED_DC_XZ_BEGIN_UPSERT = EXPECTED_BASE_XZ_UPSERT | {
    "comments": "MX-Bluesky: Xray centring 2 -",
}

EXPECTED_DC_XY_UPDATE_UPSERT = EXPECTED_BASE_XY_UPSERT | {
    "flux": 10.0,
    "synchrotronMode": "test",
}

EXPECTED_DC_XZ_UPDATE_UPSERT = EXPECTED_BASE_XZ_UPSERT | {
    "flux": 10,
    "synchrotronMode": "test",
}


@pytest.fixture
def scan_data_infos_for_begin():
    return [
        ScanDataInfo(
            data_collection_info=replace(DC_INFO_FOR_BEGIN_XY),
            data_collection_id=None,
            data_collection_position_info=None,
            data_collection_grid_info=None,
        ),
        ScanDataInfo(
            data_collection_info=replace(DC_INFO_FOR_BEGIN_XZ),
            data_collection_id=None,
            data_collection_position_info=None,
            data_collection_grid_info=None,
        ),
    ]


@pytest.fixture
def scan_data_infos_for_update():
    scan_xy_data_info_for_update = ScanDataInfo(
        data_collection_info=replace(DC_INFO_FOR_UPDATE_XY),
        data_collection_id=TEST_DATA_COLLECTION_IDS[0],
        data_collection_position_info=DataCollectionPositionInfo(
            pos_x=0, pos_y=0, pos_z=0
        ),
        data_collection_grid_info=DataCollectionGridInfo(
            dx_in_mm=0.1,
            dy_in_mm=0.1,
            steps_x=40,
            steps_y=20,
            microns_per_pixel_x=1.25,
            microns_per_pixel_y=1.25,
            snapshot_offset_x_pixel=50,
            snapshot_offset_y_pixel=100,
            orientation=Orientation.HORIZONTAL,
            snaked=True,
        ),
    )
    scan_xz_data_info_for_update = ScanDataInfo(
        data_collection_info=replace(DC_INFO_FOR_UPDATE_XZ),
        data_collection_id=TEST_DATA_COLLECTION_IDS[1],
        data_collection_position_info=DataCollectionPositionInfo(
            pos_x=0.0, pos_y=0.0, pos_z=0.0
        ),
        data_collection_grid_info=DataCollectionGridInfo(
            dx_in_mm=0.1,
            dy_in_mm=0.2,
            steps_x=40,
            steps_y=10,
            microns_per_pixel_x=1.25,
            microns_per_pixel_y=1.25,
            snapshot_offset_x_pixel=50,
            snapshot_offset_y_pixel=120,
            orientation=Orientation.HORIZONTAL,
            snaked=True,
        ),
    )
    return [scan_xy_data_info_for_update, scan_xz_data_info_for_update]


def test_ispyb_deposition_comment_for_3D_correct(
    mock_ispyb_conn: MagicMock,
    dummy_ispyb: StoreInIspyb,
    dummy_collection_group_info,
    scan_data_infos_for_begin,
    scan_data_infos_for_update,
):
    mock_ispyb_conn = mock_ispyb_conn
    mock_mx_aquisition = mx_acquisition_from_conn(mock_ispyb_conn)

    ispyb_ids = dummy_ispyb.begin_deposition(
        dummy_collection_group_info, scan_data_infos_for_begin
    )
    dummy_ispyb.update_deposition(ispyb_ids, scan_data_infos_for_update)

    first_create_dc, second_create_dc = mock_ispyb_conn.calls_for(DCS_RE)

    assert json.loads(first_create_dc.request.body)["comments"] == (
        "MX-Bluesky: Xray centring 1 -"
    )
    assert json.loads(second_create_dc.request.body)["comments"] == (
        "MX-Bluesky: Xray centring 2 -"
    )
    mock_mx_aquisition.update_data_collection_append_comments.assert_any_call(
        TEST_DATA_COLLECTION_IDS[0],
        "Diffraction grid scan of 40 by 20 images "
        "in 100.0 um by 100.0 um steps. Top left (px): [50,100], bottom right (px): [3250,1700].",
        " ",
    )
    mock_mx_aquisition.update_data_collection_append_comments.assert_any_call(
        TEST_DATA_COLLECTION_IDS[1],
        "Diffraction grid scan of 40 by 10 images "
        "in 100.0 um by 200.0 um steps. Top left (px): [50,120], bottom right (px): [3250,1720].",
        " ",
    )


def test_store_3d_grid_scan(
    mock_ispyb_conn,
    dummy_ispyb: StoreInIspyb,
    dummy_collection_group_info,
    scan_data_infos_for_begin,
    scan_data_infos_for_update,
):
    ispyb_ids = dummy_ispyb.begin_deposition(
        dummy_collection_group_info, scan_data_infos_for_begin
    )
    assert ispyb_ids == IspybIds(
        data_collection_ids=(TEST_DATA_COLLECTION_IDS[0], TEST_DATA_COLLECTION_IDS[1]),
        data_collection_group_id=TEST_DATA_COLLECTION_GROUP_ID,
    )

    assert dummy_ispyb.update_deposition(
        ispyb_ids, scan_data_infos_for_update
    ) == IspybIds(
        data_collection_ids=TEST_DATA_COLLECTION_IDS,
        data_collection_group_id=TEST_DATA_COLLECTION_GROUP_ID,
        grid_ids=TEST_GRID_INFO_IDS,
    )


@patch(
    "mx_bluesky.common.external_interaction.callbacks.common.ispyb_mapping.get_current_time_string",
    new=MagicMock(return_value=EXPECTED_START_TIME),
)
def test_begin_deposition(
    mock_ispyb_conn,
    dummy_ispyb: StoreInIspyb,
    dummy_collection_group_info,
    scan_data_infos_for_begin,
):
    assert dummy_ispyb.begin_deposition(
        dummy_collection_group_info, scan_data_infos_for_begin
    ) == IspybIds(
        data_collection_ids=(TEST_DATA_COLLECTION_IDS[0], TEST_DATA_COLLECTION_IDS[1]),
        data_collection_group_id=TEST_DATA_COLLECTION_GROUP_ID,
    )

    create_dcg_request = mock_ispyb_conn.calls_for(DCGS_RE)[0].request
    assert mock_ispyb_conn.match(create_dcg_request, DCGS_RE, 2) == TEST_PROPOSAL_REF
    assert (
        int(mock_ispyb_conn.match(create_dcg_request, DCGS_RE, 3)) == TEST_VISIT_NUMBER
    )
    dcg_payload = json.loads(create_dcg_request.body)
    assert dcg_payload["experimentType"] == "Mesh3D"
    assert dcg_payload["sampleId"] == TEST_SAMPLE_ID

    create_dc_requests = mock_ispyb_conn.calls_for(DCS_RE)
    request1 = create_dc_requests[0].request
    assert (
        int(mock_ispyb_conn.match(request1, DCS_RE, 2)) == TEST_DATA_COLLECTION_GROUP_ID
    )
    assert json.loads(request1.body) == EXPECTED_DC_XY_BEGIN_UPSERT

    request2 = create_dc_requests[1].request
    assert (
        int(mock_ispyb_conn.match(request2, DCS_RE, 2)) == TEST_DATA_COLLECTION_GROUP_ID
    )
    assert json.loads(request2.body) == EXPECTED_DC_XZ_BEGIN_UPSERT

    assert len(mock_ispyb_conn.calls_for(POSITION_RE)) == 0
    assert len(mock_ispyb_conn.calls_for(GRID_RE)) == 0


@patch(
    "mx_bluesky.common.external_interaction.callbacks.common.ispyb_mapping.get_current_time_string",
    new=MagicMock(return_value=EXPECTED_START_TIME),
)
def test_update_deposition(
    mock_ispyb_conn,
    dummy_ispyb,
    dummy_collection_group_info,
    scan_data_infos_for_begin,
    scan_data_infos_for_update,
):
    ispyb_ids = dummy_ispyb.begin_deposition(
        dummy_collection_group_info, scan_data_infos_for_begin
    )
    assert len(mock_ispyb_conn.calls_for(DCGS_RE)) == 1
    assert len(mock_ispyb_conn.calls_for(DCS_RE)) == 2
    # mx_acq.upsert_data_collection_group.reset_mock()
    # mx_acq.upsert_data_collection.reset_mock()

    dummy_collection_group_info.sample_barcode = TEST_BARCODE

    actual_rows = dummy_ispyb.update_deposition(ispyb_ids, scan_data_infos_for_update)

    assert actual_rows == IspybIds(
        data_collection_group_id=TEST_DATA_COLLECTION_GROUP_ID,
        data_collection_ids=TEST_DATA_COLLECTION_IDS,
        grid_ids=TEST_GRID_INFO_IDS,
    )

    assert len(mock_ispyb_conn.calls_for(DCGS_RE)) == 1

    update_xy_req = mock_ispyb_conn.calls_for(DC_RE)[0].request
    update_xz_req = mock_ispyb_conn.calls_for(DC_RE)[1].request

    assert (
        int(mock_ispyb_conn.match(update_xy_req, DC_RE, 2))
        == TEST_DATA_COLLECTION_IDS[0]
    )
    assert json.loads(update_xy_req.body) == EXPECTED_DC_XY_UPDATE_UPSERT
    assert (
        int(mock_ispyb_conn.match(update_xz_req, DC_RE, 2))
        == TEST_DATA_COLLECTION_IDS[1]
    )
    assert json.loads(update_xz_req.body) == EXPECTED_DC_XZ_UPDATE_UPSERT

    mx_acq = mx_acquisition_from_conn(mock_ispyb_conn)
    assert mx_acq.update_data_collection_append_comments.call_args_list[0] == (
        (
            TEST_DATA_COLLECTION_IDS[0],
            "Diffraction grid scan of 40 by 20 "
            "images in 100.0 um by 100.0 um steps. Top left (px): [50,100], "
            "bottom right (px): [3250,1700].",
            " ",
        ),
    )

    update_dc_xy_pos_req, update_dc_xz_pos_req = [
        c.request for c in mock_ispyb_conn.calls_for(POSITION_RE)
    ]
    assert (
        int(mock_ispyb_conn.match(update_dc_xy_pos_req, POSITION_RE, 2))
        == TEST_DATA_COLLECTION_IDS[0]
    )
    assert json.loads(update_dc_xz_pos_req.body) == {
        "posX": 0,
        "posY": 0,
        "posZ": 0,
    }

    update_grid_xy_req, update_grid_xz_req = [
        c.request for c in mock_ispyb_conn.calls_for(GRID_RE)
    ]
    assert (
        int(mock_ispyb_conn.match(update_grid_xy_req, GRID_RE, 2))
        == TEST_DATA_COLLECTION_IDS[0]
    )
    assert json.loads(update_grid_xy_req.body) == {
        "dx": 0.1,
        "dy": 0.1,
        "stepsX": 40,
        "stepsY": 20,
        "pixelsPerMicronX": 0.8,
        "pixelsPerMicronY": 0.8,
        "snapshotOffsetXPixel": 50,
        "snapshotOffsetYPixel": 100,
        "orientation": "horizontal",
        "snaked": True,
    }

    assert mx_acq.update_data_collection_append_comments.call_args_list[1] == (
        (
            TEST_DATA_COLLECTION_IDS[1],
            "Diffraction grid scan of 40 by 10 "
            "images in 100.0 um by 200.0 um steps. Top left (px): [50,120], "
            "bottom right (px): [3250,1720].",
            " ",
        ),
    )

    assert (
        int(mock_ispyb_conn.match(update_dc_xz_pos_req, POSITION_RE, 2))
        == TEST_DATA_COLLECTION_IDS[1]
    )
    assert json.loads(update_dc_xz_pos_req.body) == {
        "posX": 0,
        "posY": 0,
        "posZ": 0,
    }

    assert (
        int(mock_ispyb_conn.match(update_grid_xz_req, GRID_RE, 2))
        == TEST_DATA_COLLECTION_IDS[1]
    )
    assert json.loads(update_grid_xz_req.body) == {
        "dx": 0.1,
        "dy": 0.2,
        "stepsX": 40,
        "stepsY": 10,
        "pixelsPerMicronX": 0.8,
        "pixelsPerMicronY": 0.8,
        "snapshotOffsetXPixel": 50,
        "snapshotOffsetYPixel": 120,
        "orientation": "horizontal",
        "snaked": True,
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
    dummy_collection_group_info,
    scan_data_infos_for_begin,
    scan_data_infos_for_update,
):
    ispyb_ids = dummy_ispyb.begin_deposition(
        dummy_collection_group_info, scan_data_infos_for_begin
    )
    mx_acq = mx_acquisition_from_conn(mock_ispyb_conn)
    assert len(mock_ispyb_conn.calls_for(DCGS_RE)) == 1
    ispyb_ids = dummy_ispyb.update_deposition(ispyb_ids, scan_data_infos_for_update)
    assert len(mock_ispyb_conn.calls_for(DCGS_RE)) == 1
    assert len(mock_ispyb_conn.calls_for(DCS_RE)) == 2
    assert len(mock_ispyb_conn.calls_for(DC_RE)) == 2
    assert len(mock_ispyb_conn.calls_for(GRID_RE)) == 2

    get_current_time.return_value = EXPECTED_END_TIME
    dummy_ispyb.end_deposition(ispyb_ids, "success", "Test succeeded")
    mx_acq.update_data_collection_append_comments.assert_any_call(
        TEST_DATA_COLLECTION_IDS[0],
        "DataCollection Successful reason: Test succeeded",
        " ",
    )
    update_dc_requests = [c.request for c in mock_ispyb_conn.calls_for(DC_RE)[2:]]
    assert (
        int(mock_ispyb_conn.match(update_dc_requests[0], DC_RE, 2))
        == TEST_DATA_COLLECTION_IDS[0]
    )
    assert json.loads(update_dc_requests[0].body) == {
        "endTime": EXPECTED_END_TIME,
        "runStatus": "DataCollection Successful",
    }
    mx_acq.update_data_collection_append_comments.assert_any_call(
        TEST_DATA_COLLECTION_IDS[1],
        "DataCollection Successful reason: Test succeeded",
        " ",
    )
    assert (
        int(mock_ispyb_conn.match(update_dc_requests[1], DC_RE, 2))
        == TEST_DATA_COLLECTION_IDS[1]
    )
    assert json.loads(update_dc_requests[1].body) == {
        "endTime": EXPECTED_END_TIME,
        "runStatus": "DataCollection Successful",
    }


def test_param_keys(
    mock_ispyb_conn,
    dummy_ispyb,
    dummy_collection_group_info,
    scan_data_infos_for_begin,
    scan_data_infos_for_update,
):
    ispyb_ids = dummy_ispyb.begin_deposition(
        dummy_collection_group_info, scan_data_infos_for_begin
    )
    assert dummy_ispyb.update_deposition(
        ispyb_ids, scan_data_infos_for_update
    ) == IspybIds(
        data_collection_ids=(TEST_DATA_COLLECTION_IDS[0], TEST_DATA_COLLECTION_IDS[1]),
        data_collection_group_id=TEST_DATA_COLLECTION_GROUP_ID,
        grid_ids=(TEST_GRID_INFO_IDS[0], TEST_GRID_INFO_IDS[1]),
    )


def test_given_sampleid_of_none_when_grid_scan_stored_then_sample_id_not_set(
    mock_ispyb_conn,
    dummy_ispyb,
    dummy_collection_group_info,
    scan_data_infos_for_begin,
    scan_data_infos_for_update,
):
    dummy_collection_group_info.sample_id = None
    for dc_info in [
        scan_info.data_collection_info
        for scan_info in scan_data_infos_for_begin + scan_data_infos_for_update
    ]:
        dc_info.sample_id = None

    ispyb_ids = dummy_ispyb.begin_deposition(
        dummy_collection_group_info, scan_data_infos_for_begin
    )
    dummy_ispyb.update_deposition(ispyb_ids, scan_data_infos_for_update)

    dcg_requests = [c.request for c in mock_ispyb_conn.calls_for(DCGS_RE)] + [
        c.request for c in mock_ispyb_conn.calls_for(DCG_RE)
    ]
    for req in dcg_requests:
        assert "sampleId" not in json.loads(req.body)


def test_given_real_sampleid_when_grid_scan_stored_then_sample_id_set(
    mock_ispyb_conn,
    dummy_ispyb: StoreInIspyb,
    dummy_collection_group_info,
    scan_data_infos_for_begin,
    scan_data_infos_for_update,
):
    expected_sample_id = 364758

    ispyb_ids = dummy_ispyb.begin_deposition(
        dummy_collection_group_info, scan_data_infos_for_begin
    )
    dummy_ispyb.update_deposition(ispyb_ids, scan_data_infos_for_update)

    dcg_requests = [c.request for c in mock_ispyb_conn.calls_for(DCGS_RE)] + [
        c.request for c in mock_ispyb_conn.calls_for(DCG_RE)
    ]
    assert len(dcg_requests) > 0
    for req in dcg_requests:
        assert json.loads(req.body)["sampleId"] == expected_sample_id


def test_fail_result_run_results_in_bad_run_status(
    mock_ispyb_conn: MagicMock,
    dummy_ispyb: StoreInIspyb,
    dummy_collection_group_info,
    scan_data_infos_for_begin,
    scan_data_infos_for_update,
):
    mock_ispyb_conn = mock_ispyb_conn

    ispyb_ids = dummy_ispyb.begin_deposition(
        dummy_collection_group_info, scan_data_infos_for_begin
    )
    ispyb_ids = dummy_ispyb.update_deposition(ispyb_ids, scan_data_infos_for_update)
    dummy_ispyb.end_deposition(ispyb_ids, "fail", "test specifies failure")

    update_dc_requests = [c.request for c in mock_ispyb_conn.calls_for(DC_RE)]
    expected_ids_and_runstatuses = [
        (TEST_DATA_COLLECTION_IDS[0], None),
        (TEST_DATA_COLLECTION_IDS[1], None),
        (TEST_DATA_COLLECTION_IDS[0], "DataCollection Unsuccessful"),
        (TEST_DATA_COLLECTION_IDS[1], "DataCollection Unsuccessful"),
    ]
    for req, expected in zip(
        update_dc_requests, expected_ids_and_runstatuses, strict=True
    ):
        payload = json.loads(req.body)
        assert int(mock_ispyb_conn.match(req, DC_RE, 2)) == expected[0]
        assert payload.get("runStatus") == expected[1]


def test_fail_result_long_comment_still_updates_run_status(
    mock_ispyb_conn: MagicMock,
    dummy_ispyb: StoreInIspyb,
    dummy_collection_group_info,
    scan_data_infos_for_begin,
    scan_data_infos_for_update,
):
    mock_ispyb_conn = mock_ispyb_conn
    mock_mx_aquisition = mx_acquisition_from_conn(mock_ispyb_conn)
    mock_mx_aquisition.update_data_collection_append_comments.side_effect = (
        ReadWriteError("Comment too big for column")
    )

    ispyb_ids = dummy_ispyb.begin_deposition(
        dummy_collection_group_info, scan_data_infos_for_begin
    )
    ispyb_ids = dummy_ispyb.update_deposition(ispyb_ids, scan_data_infos_for_update)
    dummy_ispyb.end_deposition(ispyb_ids, "fail", "this comment is too long")

    update_dc_requests = [c.request for c in mock_ispyb_conn.calls_for(DC_RE)]
    expected_ids_and_runstatuses = [
        (TEST_DATA_COLLECTION_IDS[0], None),
        (TEST_DATA_COLLECTION_IDS[1], None),
        (TEST_DATA_COLLECTION_IDS[0], "DataCollection Unsuccessful"),
        (TEST_DATA_COLLECTION_IDS[1], "DataCollection Unsuccessful"),
    ]
    for req, expected in zip(
        update_dc_requests, expected_ids_and_runstatuses, strict=True
    ):
        payload = json.loads(req.body)
        assert int(mock_ispyb_conn.match(req, DC_RE, 2)) == expected[0]
        assert payload.get("runStatus") == expected[1]


def test_no_exception_during_run_results_in_good_run_status(
    mock_ispyb_conn: MagicMock,
    dummy_ispyb: StoreInIspyb,
    dummy_collection_group_info,
    scan_data_infos_for_begin,
    scan_data_infos_for_update,
):
    ispyb_ids = dummy_ispyb.begin_deposition(
        dummy_collection_group_info, scan_data_infos_for_begin
    )
    ispyb_ids = dummy_ispyb.update_deposition(ispyb_ids, scan_data_infos_for_update)
    dummy_ispyb.end_deposition(ispyb_ids, "success", "")

    update_dc_requests = [c.request for c in mock_ispyb_conn.calls_for(DC_RE)]
    expected_ids_and_runstatuses = [
        (TEST_DATA_COLLECTION_IDS[0], None),
        (TEST_DATA_COLLECTION_IDS[1], None),
        (TEST_DATA_COLLECTION_IDS[0], "DataCollection Successful"),
        (TEST_DATA_COLLECTION_IDS[1], "DataCollection Successful"),
    ]
    for req, expected in zip(
        update_dc_requests, expected_ids_and_runstatuses, strict=True
    ):
        payload = json.loads(req.body)
        assert int(mock_ispyb_conn.match(req, DC_RE, 2)) == expected[0]
        assert payload.get("runStatus") == expected[1]


def test_update_data_collection_no_comment(
    mock_ispyb_conn: MagicMock,
    dummy_ispyb: StoreInIspyb,
    dummy_collection_group_info: DataCollectionGroupInfo,
    scan_data_infos_for_begin: list[ScanDataInfo],
    scan_data_infos_for_update: list[ScanDataInfo],
):
    for scan_data_info in scan_data_infos_for_update:
        scan_data_info.data_collection_info.comments = None

    ispyb_ids = dummy_ispyb.begin_deposition(
        dummy_collection_group_info, scan_data_infos_for_begin
    )
    dummy_ispyb.update_deposition(ispyb_ids, scan_data_infos_for_update)

    mx_acq = mx_acquisition_from_conn(mock_ispyb_conn)
    mx_acq.update_data_collection_append_comments.assert_not_called()
