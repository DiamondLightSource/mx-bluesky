from dataclasses import replace
from functools import partial
from itertools import dropwhile
from unittest.mock import MagicMock, patch

import pytest
from ispyb.sp.mxacquisition import MXAcquisition

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
    EXPECTED_END_TIME,
    EXPECTED_START_TIME,
    TEST_BARCODE,
    TEST_DATA_COLLECTION_GROUP_ID,
    TEST_DATA_COLLECTION_IDS,
    TEST_GRID_INFO_IDS,
    TEST_SAMPLE_ID,
    TEST_SESSION_ID,
    assert_upsert_call_with,
    mx_acquisition_from_conn,
    remap_upsert_columns,
)


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
    "visitid": TEST_SESSION_ID,
    "parentid": TEST_DATA_COLLECTION_GROUP_ID,
    "sampleid": TEST_SAMPLE_ID,
    "detectorid": 78,
    "axisrange": 0,
    "focal_spot_size_at_samplex": 0.0,
    "focal_spot_size_at_sampley": 0.0,
    "slitgap_vertical": 0.1,
    "slitgap_horizontal": 0.1,
    "beamsize_at_samplex": 0.1,
    "beamsize_at_sampley": 0.1,
    "transmission": 100.0,
    "data_collection_number": 1,
    "detector_distance": 100.0,
    "exp_time": 0.1,
    "imgdir": "/tmp/",
    "imgprefix": "file_name",
    "imgsuffix": "h5",
    "n_passes": 1,
    "overlap": 0,
    "start_image_number": 1,
    "wavelength": 123.98419840550369,
    "xbeam": 150.0,
    "ybeam": 160.0,
    "undulator_gap1": 1.0,
    "starttime": EXPECTED_START_TIME,
}

EXPECTED_BASE_XY_UPSERT = EXPECTED_BASE_UPSERT | {
    "xtal_snapshot1": "test_1_y",
    "xtal_snapshot2": "test_2_y",
    "xtal_snapshot3": "test_3_y",
    "omegastart": 0,
    "axisstart": 0.0,
    "axisend": 0,
    "filetemplate": "file_name_0_master.h5",
    "nimages": 40 * 20,
}

EXPECTED_BASE_XZ_UPSERT = EXPECTED_BASE_UPSERT | {
    "xtal_snapshot1": "test_1_z",
    "xtal_snapshot2": "test_2_z",
    "xtal_snapshot3": "test_3_z",
    "omegastart": 90.0,
    "axisstart": 90.0,
    "axisend": 90.0,
    "filetemplate": "file_name_1_master.h5",
    "nimages": 40 * 10,
}

EXPECTED_DC_XY_BEGIN_UPSERT = EXPECTED_BASE_XY_UPSERT | {
    "comments": "MX-Bluesky: Xray centring 1 -",
}

EXPECTED_DC_XZ_BEGIN_UPSERT = EXPECTED_BASE_XZ_UPSERT | {
    "comments": "MX-Bluesky: Xray centring 2 -",
}

EXPECTED_DC_XY_UPDATE_UPSERT = EXPECTED_BASE_XY_UPSERT | {
    "id": 12,
    "flux": 10.0,
    "synchrotron_mode": "test",
}

EXPECTED_DC_XZ_UPDATE_UPSERT = EXPECTED_BASE_XZ_UPSERT | {
    "id": 13,
    "flux": 10,
    "synchrotron_mode": "test",
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
    mock_upsert_dc = mock_mx_aquisition.upsert_data_collection
    ispyb_ids = dummy_ispyb.begin_deposition(
        dummy_collection_group_info, scan_data_infos_for_begin
    )
    dummy_ispyb.update_deposition(ispyb_ids, scan_data_infos_for_update)

    upsert_keys = mock_mx_aquisition.get_data_collection_params()
    first_upserted_param_value_dict = remap_upsert_columns(
        upsert_keys, mock_upsert_dc.call_args_list[0][0][0]
    )
    second_upserted_param_value_dict = remap_upsert_columns(
        upsert_keys, mock_upsert_dc.call_args_list[1][0][0]
    )
    assert first_upserted_param_value_dict["comments"] == (
        "MX-Bluesky: Xray centring 1 -"
    )
    assert second_upserted_param_value_dict["comments"] == (
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

    mx_acq = mx_acquisition_from_conn(mock_ispyb_conn)
    assert_upsert_call_with(
        mx_acq.upsert_data_collection_group.mock_calls[0],
        mx_acq.get_data_collection_group_params(),
        {
            "parentid": TEST_SESSION_ID,
            "experimenttype": "Mesh3D",
            "sampleid": TEST_SAMPLE_ID,
        },
    )
    assert_upsert_call_with(
        mx_acq.upsert_data_collection.mock_calls[0],
        mx_acq.get_data_collection_params(),
        EXPECTED_DC_XY_BEGIN_UPSERT,
    )
    assert_upsert_call_with(
        mx_acq.upsert_data_collection.mock_calls[1],
        mx_acq.get_data_collection_params(),
        EXPECTED_DC_XZ_BEGIN_UPSERT,
    )
    mx_acq.update_dc_position.assert_not_called()
    mx_acq.upsert_dc_grid.assert_not_called()


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
    mx_acq = mx_acquisition_from_conn(mock_ispyb_conn)
    mx_acq.upsert_data_collection_group.assert_called_once()
    mx_acq.upsert_data_collection.assert_called()
    mx_acq.upsert_data_collection_group.reset_mock()
    mx_acq.upsert_data_collection.reset_mock()

    dummy_collection_group_info.sample_barcode = TEST_BARCODE

    actual_rows = dummy_ispyb.update_deposition(ispyb_ids, scan_data_infos_for_update)

    assert actual_rows == IspybIds(
        data_collection_group_id=TEST_DATA_COLLECTION_GROUP_ID,
        data_collection_ids=TEST_DATA_COLLECTION_IDS,
        grid_ids=TEST_GRID_INFO_IDS,
    )

    mx_acq.upsert_data_collection_group.assert_not_called()

    assert_upsert_call_with(
        mx_acq.upsert_data_collection.mock_calls[0],
        mx_acq.get_data_collection_params(),
        EXPECTED_DC_XY_UPDATE_UPSERT,
    )

    assert mx_acq.update_data_collection_append_comments.call_args_list[0] == (
        (
            TEST_DATA_COLLECTION_IDS[0],
            "Diffraction grid scan of 40 by 20 "
            "images in 100.0 um by 100.0 um steps. Top left (px): [50,100], "
            "bottom right (px): [3250,1700].",
            " ",
        ),
    )

    assert_upsert_call_with(
        mx_acq.update_dc_position.mock_calls[0],
        mx_acq.get_dc_position_params(),
        {
            "id": TEST_DATA_COLLECTION_IDS[0],
            "pos_x": 0,
            "pos_y": 0,
            "pos_z": 0,
        },
    )

    assert_upsert_call_with(
        mx_acq.upsert_dc_grid.mock_calls[0],
        mx_acq.get_dc_grid_params(),
        {
            "parentid": TEST_DATA_COLLECTION_IDS[0],
            "dxinmm": 0.1,
            "dyinmm": 0.1,
            "stepsx": 40,
            "stepsy": 20,
            "micronsperpixelx": 1.25,
            "micronsperpixely": 1.25,
            "snapshotoffsetxpixel": 50,
            "snapshotoffsetypixel": 100,
            "orientation": "horizontal",
            "snaked": True,
        },
    )

    assert_upsert_call_with(
        mx_acq.upsert_data_collection.mock_calls[1],
        mx_acq.get_data_collection_params(),
        EXPECTED_DC_XZ_UPDATE_UPSERT,
    )

    assert mx_acq.update_data_collection_append_comments.call_args_list[1] == (
        (
            TEST_DATA_COLLECTION_IDS[1],
            "Diffraction grid scan of 40 by 10 "
            "images in 100.0 um by 200.0 um steps. Top left (px): [50,120], "
            "bottom right (px): [3250,1720].",
            " ",
        ),
    )

    assert_upsert_call_with(
        mx_acq.update_dc_position.mock_calls[1],
        mx_acq.get_dc_position_params(),
        {
            "id": TEST_DATA_COLLECTION_IDS[1],
            "pos_x": 0,
            "pos_y": 0,
            "pos_z": 0,
        },
    )

    assert_upsert_call_with(
        mx_acq.upsert_dc_grid.mock_calls[1],
        mx_acq.get_dc_grid_params(),
        {
            "parentid": TEST_DATA_COLLECTION_IDS[1],
            "dxinmm": 0.1,
            "dyinmm": 0.2,
            "stepsx": 40,
            "stepsy": 10,
            "micronsperpixelx": 1.25,
            "micronsperpixely": 1.25,
            "snapshotoffsetxpixel": 50,
            "snapshotoffsetypixel": 120,
            "orientation": "horizontal",
            "snaked": True,
        },
    )


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
    assert len(mx_acq.upsert_data_collection_group.mock_calls) == 1
    ispyb_ids = dummy_ispyb.update_deposition(ispyb_ids, scan_data_infos_for_update)
    assert len(mx_acq.upsert_data_collection_group.mock_calls) == 1
    assert len(mx_acq.upsert_data_collection.mock_calls) == 4
    assert len(mx_acq.upsert_dc_grid.mock_calls) == 2

    get_current_time.return_value = EXPECTED_END_TIME
    dummy_ispyb.end_deposition(ispyb_ids, "success", "Test succeeded")
    mx_acq.update_data_collection_append_comments.assert_any_call(
        TEST_DATA_COLLECTION_IDS[0],
        "DataCollection Successful reason: Test succeeded",
        " ",
    )
    assert_upsert_call_with(
        mx_acq.upsert_data_collection.mock_calls[4],
        mx_acq.get_data_collection_params(),
        {
            "id": TEST_DATA_COLLECTION_IDS[0],
            "parentid": TEST_DATA_COLLECTION_GROUP_ID,
            "endtime": EXPECTED_END_TIME,
            "runstatus": "DataCollection Successful",
        },
    )
    mx_acq.update_data_collection_append_comments.assert_any_call(
        TEST_DATA_COLLECTION_IDS[1],
        "DataCollection Successful reason: Test succeeded",
        " ",
    )
    assert_upsert_call_with(
        mx_acq.upsert_data_collection.mock_calls[5],
        mx_acq.get_data_collection_params(),
        {
            "id": TEST_DATA_COLLECTION_IDS[1],
            "parentid": TEST_DATA_COLLECTION_GROUP_ID,
            "endtime": EXPECTED_END_TIME,
            "runstatus": "DataCollection Successful",
        },
    )


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


def _test_when_grid_scan_stored_then_data_present_in_upserts(
    ispyb_conn,
    dummy_ispyb,
    test_function,
    dummy_collection_group_info,
    scan_data_infos_for_begin,
    scan_data_infos_for_update,
    test_group=False,
):
    ispyb_ids = dummy_ispyb.begin_deposition(
        dummy_collection_group_info, scan_data_infos_for_begin
    )
    dummy_ispyb.update_deposition(ispyb_ids, scan_data_infos_for_update)

    mx_acquisition = mx_acquisition_from_conn(ispyb_conn)

    def call_does_not_have_dcid(id, func_call):
        return func_call.args[0][0] != id

    for dc_id in ispyb_ids.data_collection_ids:
        upsert_call = next(
            dropwhile(
                partial(call_does_not_have_dcid, dc_id),
                mx_acquisition.upsert_data_collection.call_args_list,
            )
        )
        actual = upsert_call[0][0]
        assert test_function(MXAcquisition.get_data_collection_params(), actual)

    if test_group:
        upsert_data_collection_group_arg_list = (
            mx_acquisition.upsert_data_collection_group.call_args_list[0][0]
        )
        actual = upsert_data_collection_group_arg_list[0]
        assert test_function(MXAcquisition.get_data_collection_group_params(), actual)


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

    def test_sample_id(default_params, actual):
        sampleid_idx = list(default_params).index("sampleid")
        return actual[sampleid_idx] == default_params["sampleid"]

    _test_when_grid_scan_stored_then_data_present_in_upserts(
        mock_ispyb_conn,
        dummy_ispyb,
        test_sample_id,
        dummy_collection_group_info,
        scan_data_infos_for_begin,
        scan_data_infos_for_update,
        True,
    )


def test_given_real_sampleid_when_grid_scan_stored_then_sample_id_set(
    mock_ispyb_conn,
    dummy_ispyb: StoreInIspyb,
    dummy_collection_group_info,
    scan_data_infos_for_begin,
    scan_data_infos_for_update,
):
    expected_sample_id = 364758

    def test_sample_id(default_params, actual):
        sampleid_idx = list(default_params).index("sampleid")
        return actual[sampleid_idx] == expected_sample_id

    _test_when_grid_scan_stored_then_data_present_in_upserts(
        mock_ispyb_conn,
        dummy_ispyb,
        test_sample_id,
        dummy_collection_group_info,
        scan_data_infos_for_begin,
        scan_data_infos_for_update,
        True,
    )


def test_fail_result_run_results_in_bad_run_status(
    mock_ispyb_conn: MagicMock,
    dummy_ispyb: StoreInIspyb,
    dummy_collection_group_info,
    scan_data_infos_for_begin,
    scan_data_infos_for_update,
):
    mock_ispyb_conn = mock_ispyb_conn
    mock_mx_aquisition = (
        mock_ispyb_conn.return_value.__enter__.return_value.mx_acquisition
    )
    mock_upsert_data_collection = mock_mx_aquisition.upsert_data_collection

    ispyb_ids = dummy_ispyb.begin_deposition(
        dummy_collection_group_info, scan_data_infos_for_begin
    )
    ispyb_ids = dummy_ispyb.update_deposition(ispyb_ids, scan_data_infos_for_update)
    dummy_ispyb.end_deposition(ispyb_ids, "fail", "test specifies failure")

    mock_upsert_data_collection_calls = mock_upsert_data_collection.call_args_list
    for upsert_call in mock_upsert_data_collection_calls[4:5]:
        end_deposition_upsert_args = upsert_call[0]
        upserted_param_value_list = end_deposition_upsert_args[0]
        assert "DataCollection Unsuccessful" in upserted_param_value_list
        assert "DataCollection Successful" not in upserted_param_value_list


def test_no_exception_during_run_results_in_good_run_status(
    mock_ispyb_conn: MagicMock,
    dummy_ispyb: StoreInIspyb,
    dummy_collection_group_info,
    scan_data_infos_for_begin,
    scan_data_infos_for_update,
):
    mock_mx_acquisition = (
        mock_ispyb_conn.return_value.__enter__.return_value.mx_acquisition
    )
    mock_upsert_data_collection = mock_mx_acquisition.upsert_data_collection

    ispyb_ids = dummy_ispyb.begin_deposition(
        dummy_collection_group_info, scan_data_infos_for_begin
    )
    ispyb_ids = dummy_ispyb.update_deposition(ispyb_ids, scan_data_infos_for_update)
    dummy_ispyb.end_deposition(ispyb_ids, "success", "")

    mock_upsert_data_collection_calls = mock_upsert_data_collection.call_args_list
    for upsert_call in mock_upsert_data_collection_calls[4:5]:
        end_deposition_upsert_args = upsert_call[0]
        upserted_param_value_list = end_deposition_upsert_args[0]
        assert "DataCollection Unsuccessful" not in upserted_param_value_list
        assert "DataCollection Successful" in upserted_param_value_list


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
