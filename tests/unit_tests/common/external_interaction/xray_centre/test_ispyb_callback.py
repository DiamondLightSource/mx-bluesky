from unittest.mock import MagicMock, patch

from mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback import (
    GridscanISPyBCallback,
)
from mx_bluesky.hyperion.parameters.gridscan import GridCommonWithHyperionDetectorParams

from .....conftest import (
    EXPECTED_START_TIME,
    TEST_DATA_COLLECTION_GROUP_ID,
    TEST_DATA_COLLECTION_IDS,
    TEST_RESULT_MEDIUM,
    TEST_SAMPLE_ID,
    TEST_SESSION_ID,
    TestData,
    assert_upsert_call_with,
    generate_xrc_result_event,
    mx_acquisition_from_conn,
    remap_upsert_columns,
)

EXPECTED_DATA_COLLECTION_3D_XY = {
    "visitid": TEST_SESSION_ID,
    "parentid": TEST_DATA_COLLECTION_GROUP_ID,
    "sampleid": TEST_SAMPLE_ID,
    "comments": "MX-Bluesky: Xray centring 1 -",
    "detectorid": 78,
    "data_collection_number": 1,
    "detector_distance": 100.0,
    "exp_time": 0.1,
    "imgdir": "/tmp/",
    "imgprefix": "file_name",
    "imgsuffix": "h5",
    "n_passes": 1,
    "overlap": 0,
    "start_image_number": 1,
    "wavelength": None,
    "xbeam": 150.0,
    "ybeam": 160.0,
    "synchrotron_mode": None,
    "undulator_gap1": None,
    "starttime": EXPECTED_START_TIME,
    "filetemplate": "file_name_1_master.h5",
}

EXPECTED_DATA_COLLECTION_3D_XZ = EXPECTED_DATA_COLLECTION_3D_XY | {
    "comments": "MX-Bluesky: Xray centring 2 -",
    "data_collection_number": 2,
    "filetemplate": "file_name_2_master.h5",
}


TEST_GRID_INFO_IDS = (56, 57)
TEST_POSITION_ID = 78

EXPECTED_END_TIME = "2024-02-08 14:04:01"


@patch(
    "mx_bluesky.common.external_interaction.callbacks.common.ispyb_mapping.get_current_time_string",
    new=MagicMock(return_value=EXPECTED_START_TIME),
)
class TestXrayCentreISPyBCallback:
    def test_activity_gated_start_3d(self, mock_ispyb_conn):
        callback = GridscanISPyBCallback(
            param_type=GridCommonWithHyperionDetectorParams
        )
        callback.activity_gated_start(TestData.test_gridscan3d_start_document)  # pyright: ignore
        mx_acq = mx_acquisition_from_conn(mock_ispyb_conn)
        assert_upsert_call_with(
            mx_acq.upsert_data_collection_group.mock_calls[0],  # pyright: ignore
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
            EXPECTED_DATA_COLLECTION_3D_XY,
        )
        assert_upsert_call_with(
            mx_acq.upsert_data_collection.mock_calls[1],
            mx_acq.get_data_collection_params(),
            EXPECTED_DATA_COLLECTION_3D_XZ,
        )
        mx_acq.upsert_data_collection.update_dc_position.assert_not_called()
        mx_acq.upsert_data_collection.upsert_dc_grid.assert_not_called()

    def test_reason_provided_if_crystal_not_found_error(self, mock_ispyb_conn):
        callback = GridscanISPyBCallback(
            param_type=GridCommonWithHyperionDetectorParams
        )
        callback.activity_gated_start(TestData.test_gridscan3d_start_document)  # pyright: ignore
        mx_acq = mx_acquisition_from_conn(mock_ispyb_conn)
        callback.activity_gated_stop(
            TestData.test_gridscan3d_stop_document_with_crystal_exception
        )
        assert mx_acq.update_data_collection_append_comments.call_args_list[0] == (
            (
                TEST_DATA_COLLECTION_IDS[0],
                "DataCollection Unsuccessful reason: Diffraction not found, skipping sample.",
                " ",
            ),
        )

    def test_hardware_read_event_3d(self, mock_ispyb_conn):
        callback = GridscanISPyBCallback(
            param_type=GridCommonWithHyperionDetectorParams
        )
        callback.activity_gated_start(TestData.test_gridscan3d_start_document)  # pyright: ignore
        mx_acq = mx_acquisition_from_conn(mock_ispyb_conn)
        mx_acq.upsert_data_collection_group.reset_mock()
        mx_acq.upsert_data_collection.reset_mock()
        callback.activity_gated_descriptor(
            TestData.test_descriptor_document_pre_data_collection
        )
        callback.activity_gated_event(TestData.test_event_document_pre_data_collection)
        mx_acq.upsert_data_collection_group.assert_called_once()
        expected_upsert = {
            "parentid": TEST_DATA_COLLECTION_GROUP_ID,
            "slitgaphorizontal": 0.1234,
            "slitgapvertical": 0.2345,
            "synchrotronmode": "User",
            "undulatorgap1": 1.234,
            "resolution": 1.1830593331191241,
            "wavelength": 1.11647184541378,
        }
        assert_upsert_call_with(
            mx_acq.upsert_data_collection.mock_calls[0],
            mx_acq.get_data_collection_params(),
            {"id": TEST_DATA_COLLECTION_IDS[0], **expected_upsert},
        )
        assert_upsert_call_with(
            mx_acq.upsert_data_collection.mock_calls[1],
            mx_acq.get_data_collection_params(),
            {"id": TEST_DATA_COLLECTION_IDS[1], **expected_upsert},
        )

    def test_flux_read_events_3d(self, mock_ispyb_conn):
        callback = GridscanISPyBCallback(
            param_type=GridCommonWithHyperionDetectorParams
        )
        callback.activity_gated_start(TestData.test_gridscan3d_start_document)  # pyright: ignore
        mx_acq = mx_acquisition_from_conn(mock_ispyb_conn)
        callback.activity_gated_descriptor(
            TestData.test_descriptor_document_pre_data_collection
        )
        callback.activity_gated_event(TestData.test_event_document_pre_data_collection)
        mx_acq.upsert_data_collection_group.reset_mock()
        mx_acq.upsert_data_collection.reset_mock()

        callback.activity_gated_descriptor(
            TestData.test_descriptor_document_during_data_collection
        )
        callback.activity_gated_event(
            TestData.test_event_document_during_data_collection
        )

        assert_upsert_call_with(
            mx_acq.upsert_data_collection.mock_calls[0],
            mx_acq.get_data_collection_params(),
            {
                "parentid": TEST_DATA_COLLECTION_GROUP_ID,
                "id": TEST_DATA_COLLECTION_IDS[0],
                "wavelength": 1.11647184541378,
                "transmission": 100,
                "flux": 10,
                "resolution": 1.1830593331191241,
                "focal_spot_size_at_samplex": 0.05,
                "focal_spot_size_at_sampley": 0.02,
                "beamsize_at_samplex": 0.05,
                "beamsize_at_sampley": 0.02,
            },
        )
        assert_upsert_call_with(
            mx_acq.upsert_data_collection.mock_calls[1],
            mx_acq.get_data_collection_params(),
            {
                "parentid": TEST_DATA_COLLECTION_GROUP_ID,
                "id": TEST_DATA_COLLECTION_IDS[1],
                "wavelength": 1.11647184541378,
                "transmission": 100,
                "flux": 10,
                "resolution": 1.1830593331191241,
                "focal_spot_size_at_samplex": 0.05,
                "focal_spot_size_at_sampley": 0.02,
                "beamsize_at_samplex": 0.05,
                "beamsize_at_sampley": 0.02,
            },
        )
        mx_acq.update_dc_position.assert_not_called()
        mx_acq.upsert_dc_grid.assert_not_called()

    def test_activity_gated_event_oav_snapshot_triggered(self, mock_ispyb_conn):
        callback = GridscanISPyBCallback(
            param_type=GridCommonWithHyperionDetectorParams
        )
        callback.activity_gated_start(TestData.test_gridscan3d_start_document)  # pyright: ignore
        mx_acq = mx_acquisition_from_conn(mock_ispyb_conn)
        mx_acq.upsert_data_collection_group.reset_mock()
        mx_acq.upsert_data_collection.reset_mock()

        callback.activity_gated_descriptor(
            TestData.test_descriptor_document_oav_snapshot
        )
        callback.activity_gated_event(TestData.test_event_document_oav_snapshot_xy)
        callback.activity_gated_event(TestData.test_event_document_oav_snapshot_xz)

        assert_upsert_call_with(
            mx_acq.upsert_data_collection.mock_calls[0],
            mx_acq.get_data_collection_params(),
            {
                "id": TEST_DATA_COLLECTION_IDS[0],
                "parentid": TEST_DATA_COLLECTION_GROUP_ID,
                "nimages": 40 * 20,
                "xtal_snapshot1": "test_1_y",
                "xtal_snapshot2": "test_2_y",
                "xtal_snapshot3": "test_3_y",
                "axisstart": 0,
                "omegastart": 0,
                "axisend": 0,
                "axisrange": 0,
            },
        )
        mx_acq.update_data_collection_append_comments.assert_any_call(
            TEST_DATA_COLLECTION_IDS[0],
            "Diffraction grid scan of 40 by 20 "
            "images in 126.4 um by 126.4 um steps. Top left (px): [50,100], "
            "bottom right (px): [3250,1700].",
            " ",
        )
        assert_upsert_call_with(
            mx_acq.upsert_data_collection.mock_calls[1],
            mx_acq.get_data_collection_params(),
            {
                "id": TEST_DATA_COLLECTION_IDS[1],
                "parentid": TEST_DATA_COLLECTION_GROUP_ID,
                "nimages": 40 * 10,
                "xtal_snapshot1": "test_1_z",
                "xtal_snapshot2": "test_2_z",
                "xtal_snapshot3": "test_3_z",
                "axisstart": 90,
                "omegastart": 90,
                "axisend": 90,
                "axisrange": 0,
            },
        )
        mx_acq.update_data_collection_append_comments.assert_any_call(
            TEST_DATA_COLLECTION_IDS[1],
            "Diffraction grid scan of 40 by 10 "
            "images in 126.4 um by 126.4 um steps. Top left (px): [50,0], "
            "bottom right (px): [3250,800].",
            " ",
        )
        assert_upsert_call_with(
            mx_acq.upsert_dc_grid.mock_calls[0],
            mx_acq.get_dc_grid_params(),
            {
                "parentid": TEST_DATA_COLLECTION_IDS[0],
                "dxinmm": 0.1264,
                "dyinmm": 0.1264,
                "stepsx": 40,
                "stepsy": 20,
                "micronsperpixelx": 1.58,
                "micronsperpixely": 1.58,
                "snapshotoffsetxpixel": 50,
                "snapshotoffsetypixel": 100,
                "orientation": "horizontal",
                "snaked": True,
            },
        )
        assert_upsert_call_with(
            mx_acq.upsert_dc_grid.mock_calls[1],
            mx_acq.get_dc_grid_params(),
            {
                "parentid": TEST_DATA_COLLECTION_IDS[1],
                "dxinmm": 0.1264,
                "dyinmm": 0.1264,
                "stepsx": 40,
                "stepsy": 10,
                "micronsperpixelx": 1.58,
                "micronsperpixely": 1.58,
                "snapshotoffsetxpixel": 50,
                "snapshotoffsetypixel": 0,
                "orientation": "horizontal",
                "snaked": True,
            },
        )

        assert (
            "Diffraction grid scan of 40 by 20 by 10."
            in mx_acq.upsert_data_collection_group.call_args.args[0]
        )

    def test_activity_gated_start_first_gridscan_comment_is_first_lexicographically(
        self, mock_ispyb_conn
    ):
        callback = GridscanISPyBCallback(
            param_type=GridCommonWithHyperionDetectorParams
        )
        callback.activity_gated_start(TestData.test_gridscan3d_start_document)  # pyright: ignore
        mx_acq = mx_acquisition_from_conn(mock_ispyb_conn)
        upsert_dc_1 = mx_acq.upsert_data_collection.mock_calls[0]
        upsert_dc_2 = mx_acq.upsert_data_collection.mock_calls[1]

        dc_1_cols = remap_upsert_columns(
            mx_acq.get_data_collection_params(), upsert_dc_1.args[0]
        )
        dc_2_cols = remap_upsert_columns(
            mx_acq.get_data_collection_params(), upsert_dc_2.args[0]
        )
        assert dc_1_cols["comments"] < dc_2_cols["comments"]

    def test_zocalo_read_event_appends_comment_to_first_data_collection(
        self,
        mock_ispyb_conn,
    ):
        zocalo_read_event_comment = "Crystal 1: Strength 100000; Position (grid boxes) ['1', '2', '3']; Size (grid boxes) [2 2 1]; "
        callback = GridscanISPyBCallback(
            param_type=GridCommonWithHyperionDetectorParams
        )
        zocalo_read_event = TestData.test_zocalo_reading_event | {
            "data": generate_xrc_result_event("zocalo", TEST_RESULT_MEDIUM)
        }

        callback.activity_gated_start(TestData.test_gridscan3d_start_document)
        callback.activity_gated_descriptor(
            TestData.test_descriptor_document_zocalo_reading
        )
        callback.activity_gated_event(zocalo_read_event)  # type: ignore

        mx_acq = mx_acquisition_from_conn(mock_ispyb_conn)
        mx_acq.update_data_collection_append_comments.assert_any_call(
            TEST_DATA_COLLECTION_IDS[0],
            zocalo_read_event_comment,
            " ",
        )

        assert (
            zocalo_read_event_comment
            in mx_acq.upsert_data_collection_group.call_args.args[0]
        )
