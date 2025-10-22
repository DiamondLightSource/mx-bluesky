import json
from contextlib import nullcontext
from unittest.mock import MagicMock, patch

import pytest
from bluesky.preprocessors import run_decorator, subs_decorator
from ophyd_async.core import init_devices
from ophyd_async.epics.core import epics_signal_rw

from mx_bluesky.common.experiment_plans.inner_plans.read_hardware import (
    read_hardware_plan,
)
from mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback import (
    GridscanISPyBCallback,
    GridscanPlane,
    _smargon_omega_to_xyxz_plane,
)
from mx_bluesky.common.parameters.constants import DocDescriptorNames
from mx_bluesky.hyperion.parameters.gridscan import GridCommonWithHyperionDetectorParams

from .....conftest import (
    DC_COMMENT_RE,
    DC_RE,
    DCG_RE,
    DCGS_RE,
    DCS_RE,
    EXPECTED_START_TIME,
    GRID_RE,
    POSITION_RE,
    TEST_DATA_COLLECTION_GROUP_ID,
    TEST_DATA_COLLECTION_IDS,
    TEST_SAMPLE_ID,
    replace_all_tmp_paths,
)
from ..callbacks.ispyb.test_gridscan_ispyb_store_3d import (
    TEST_PROPOSAL_REF,
    TEST_VISIT_NUMBER,
)

EXPECTED_DATA_COLLECTION_3D_XY = {
    "comments": "MX-Bluesky: Xray centring 1 -",
    "detectorId": 78,
    "detectorDistance": 100.0,
    "exposureTime": 0.1,
    "imageDirectory": "{tmp_data}/",
    "imagePrefix": "file_name",
    "imageSuffix": "h5",
    "numberOfPasses": 1,
    "overlap": 0,
    "startImageNumber": 1,
    "xBeam": 150.0,
    "yBeam": 160.0,
    "startTime": EXPECTED_START_TIME,
}

EXPECTED_DATA_COLLECTION_3D_XZ = EXPECTED_DATA_COLLECTION_3D_XY | {
    "comments": "MX-Bluesky: Xray centring 2 -",
}


TEST_GRID_INFO_IDS = (56, 57)

EXPECTED_END_TIME = "2024-02-08 14:04:01"


@patch(
    "mx_bluesky.common.external_interaction.callbacks.common.ispyb_mapping.get_current_time_string",
    new=MagicMock(return_value=EXPECTED_START_TIME),
)
class TestXrayCentreISPyBCallback:
    def test_activity_gated_start_3d(self, mock_ispyb_conn, TestEventData, tmp_path):
        callback = GridscanISPyBCallback(
            param_type=GridCommonWithHyperionDetectorParams
        )
        callback.activity_gated_start(
            TestEventData.test_grid_detect_and_gridscan_start_document
        )  # pyright: ignore
        create_dcg_request = mock_ispyb_conn.calls_for(DCGS_RE)[0].request
        assert (
            mock_ispyb_conn.match(create_dcg_request, DCGS_RE, 2) == TEST_PROPOSAL_REF
        )
        assert (
            int(mock_ispyb_conn.match(create_dcg_request, DCGS_RE, 3))
            == TEST_VISIT_NUMBER
        )
        assert json.loads(create_dcg_request.body) == {
            "experimentType": "Mesh3D",
            "sampleId": TEST_SAMPLE_ID,
        }
        create_dc_requests = [c.request for c in mock_ispyb_conn.calls_for(DCS_RE)]
        assert (
            int(mock_ispyb_conn.match(create_dc_requests[0], DCS_RE, 2))
            == TEST_DATA_COLLECTION_GROUP_ID
        )
        assert (
            int(mock_ispyb_conn.match(create_dc_requests[1], DCS_RE, 2))
            == TEST_DATA_COLLECTION_GROUP_ID
        )
        assert json.loads(create_dc_requests[0].body) == replace_all_tmp_paths(
            EXPECTED_DATA_COLLECTION_3D_XY, tmp_path
        )
        assert json.loads(create_dc_requests[1].body) == replace_all_tmp_paths(
            EXPECTED_DATA_COLLECTION_3D_XZ, tmp_path
        )

        assert len(mock_ispyb_conn.calls_for(POSITION_RE)) == 0
        assert len(mock_ispyb_conn.calls_for(GRID_RE)) == 0

    @patch(
        "mx_bluesky.common.external_interaction.ispyb.ispyb_store.StoreInIspyb.update_data_collection_group_table",
    )
    def test_reason_provided_if_crystal_not_found_error(
        self, mock_update_data_collection_group_table, mock_ispyb_conn, TestEventData
    ):
        callback = GridscanISPyBCallback(
            param_type=GridCommonWithHyperionDetectorParams
        )
        callback.activity_gated_start(
            TestEventData.test_grid_detect_and_gridscan_start_document
        )  # pyright: ignore
        callback.activity_gated_stop(
            TestEventData.test_grid_detect_and_gridscan_stop_document_with_crystal_exception
        )
        dcids_to_comment_requests = {
            r.dcid: r for r in mock_ispyb_conn.dc_calls_for(DC_COMMENT_RE)
        }
        assert dcids_to_comment_requests[TEST_DATA_COLLECTION_IDS[0]].body == {
            "comments": " DataCollection Unsuccessful reason: Diffraction not found, skipping sample.",
        }
        assert (
            mock_update_data_collection_group_table.call_args_list[0][0][0].comments
            == "Diffraction not found, skipping sample."
        )

    def test_hardware_read_event_3d(self, mock_ispyb_conn, TestEventData):
        callback = GridscanISPyBCallback(
            param_type=GridCommonWithHyperionDetectorParams
        )
        callback.activity_gated_start(
            TestEventData.test_grid_detect_and_gridscan_start_document
        )  # pyright: ignore
        callback.activity_gated_descriptor(
            TestEventData.test_descriptor_document_pre_data_collection
        )
        callback.activity_gated_event(
            TestEventData.test_event_document_pre_data_collection
        )
        assert len(mock_ispyb_conn.calls_for(DCG_RE)) == 1

        expected_upsert = {
            "slitGapHorizontal": 0.1234,
            "slitGapVertical": 0.2345,
            "synchrotronMode": "User",
            "undulatorGap1": 1.234,
            "resolution": 1.1830593331191241,
            "wavelength": 1.11647184541378,
        }
        update_dc_requests = mock_ispyb_conn.dc_calls_for(DC_RE)
        assert update_dc_requests[0].dcid == TEST_DATA_COLLECTION_IDS[0]
        assert update_dc_requests[1].dcid == TEST_DATA_COLLECTION_IDS[1]
        assert update_dc_requests[0].body == expected_upsert
        assert update_dc_requests[1].body == expected_upsert

    def test_flux_read_events_3d(self, mock_ispyb_conn, TestEventData):
        callback = GridscanISPyBCallback(
            param_type=GridCommonWithHyperionDetectorParams
        )
        callback.activity_gated_start(
            TestEventData.test_grid_detect_and_gridscan_start_document
        )  # pyright: ignore
        callback.activity_gated_descriptor(
            TestEventData.test_descriptor_document_pre_data_collection
        )
        callback.activity_gated_event(
            TestEventData.test_event_document_pre_data_collection
        )

        callback.activity_gated_descriptor(
            TestEventData.test_descriptor_document_during_data_collection
        )
        callback.activity_gated_event(
            TestEventData.test_event_document_during_data_collection
        )

        update_dc_requests = mock_ispyb_conn.dc_calls_for(DC_RE)[2:]
        expected_payload = {
            "wavelength": 1.11647184541378,
            "transmission": 100,
            "flux": 10,
            "resolution": 1.1830593331191241,
            "beamSizeAtSampleX": 0.05,
            "beamSizeAtSampleY": 0.02,
        }
        assert update_dc_requests[0].dcid == TEST_DATA_COLLECTION_IDS[0]
        assert update_dc_requests[1].dcid == TEST_DATA_COLLECTION_IDS[1]
        assert update_dc_requests[0].body == expected_payload
        assert update_dc_requests[1].body == expected_payload
        assert len(mock_ispyb_conn.calls_for(POSITION_RE)) == 0
        assert len(mock_ispyb_conn.calls_for(GRID_RE)) == 0

    @pytest.mark.parametrize(
        "snapshot_events, first_comment",
        [
            [
                [
                    "test_event_document_oav_snapshot_xy",
                    "test_event_document_oav_snapshot_xz",
                ],
                "Diffraction grid scan of 40 by 20 by _.",
            ],
            [
                [
                    "test_event_document_oav_snapshot_xz",
                    "test_event_document_oav_snapshot_xy",
                ],
                "Diffraction grid scan of 40 by _ by 10.",
            ],
        ],
        ids=["xy-then-xz", "xz-then-xy"],
    )
    def test_activity_gated_event_oav_snapshot_triggered(
        self,
        mock_ispyb_conn,
        TestEventData,
        snapshot_events: list[str],
        first_comment: str,
    ):
        callback = GridscanISPyBCallback(
            param_type=GridCommonWithHyperionDetectorParams
        )
        callback.activity_gated_start(
            TestEventData.test_grid_detect_and_gridscan_start_document
        )  # pyright: ignore

        callback.activity_gated_descriptor(
            TestEventData.test_descriptor_document_oav_snapshot
        )
        for event in [
            getattr(TestEventData, event_name) for event_name in snapshot_events
        ]:
            callback.activity_gated_event(event)

        ids_to_dc_upsert_requests = {
            r.dcid: r for r in mock_ispyb_conn.dc_calls_for(DC_RE)
        }
        assert ids_to_dc_upsert_requests[TEST_DATA_COLLECTION_IDS[0]].body == {
            "numberOfImages": 40 * 20,
            "xtalSnapshotFullPath1": "test_1_y",
            "xtalSnapshotFullPath2": "test_2_y",
            "xtalSnapshotFullPath3": "test_3_y",
            "axisStart": 0,
            "omegaStart": 0,
            "axisEnd": 0,
            "axisRange": 0,
            "dataCollectionNumber": 1,
            "fileTemplate": "file_name_1_master.h5",
        }
        dcids_to_append_comment_reqs = {
            r.dcid: r for r in mock_ispyb_conn.dc_calls_for(DC_COMMENT_RE)
        }
        assert dcids_to_append_comment_reqs[TEST_DATA_COLLECTION_IDS[0]].body == {
            "comments": " Diffraction grid scan of 40 by 20 "
            "images in 126.4 um by 126.4 um steps. Top left (px): [50,100], "
            "bottom right (px): [3250,1700].",
        }
        assert ids_to_dc_upsert_requests[TEST_DATA_COLLECTION_IDS[1]].body == {
            "numberOfImages": 40 * 10,
            "xtalSnapshotFullPath1": "test_1_z",
            "xtalSnapshotFullPath2": "test_2_z",
            "xtalSnapshotFullPath3": "test_3_z",
            "axisStart": 90,
            "omegaStart": 90,
            "axisEnd": 90,
            "axisRange": 0,
            "dataCollectionNumber": 2,
            "fileTemplate": "file_name_2_master.h5",
        }
        assert dcids_to_append_comment_reqs[TEST_DATA_COLLECTION_IDS[1]].body == {
            "comments": " Diffraction grid scan of 40 by 10 "
            "images in 126.4 um by 126.4 um steps. Top left (px): [50,0], "
            "bottom right (px): [3250,800].",
        }
        ids_to_grid_upsert_requests = {
            rq.dcid: rq for rq in (mock_ispyb_conn.dc_calls_for(GRID_RE))
        }
        assert ids_to_grid_upsert_requests[TEST_DATA_COLLECTION_IDS[0]].body == {
            "dx": 0.1264,
            "dy": 0.1264,
            "stepsX": 40,
            "stepsY": 20,
            "pixelsPerMicronX": 1 / 1.58,
            "pixelsPerMicronY": 1 / 1.58,
            "snapshotOffsetXPixel": 50,
            "snapshotOffsetYPixel": 100,
            "orientation": "horizontal",
            "snaked": True,
        }
        assert ids_to_grid_upsert_requests[TEST_DATA_COLLECTION_IDS[1]].body == {
            "dx": 0.1264,
            "dy": 0.1264,
            "stepsX": 40,
            "stepsY": 10,
            "pixelsPerMicronX": 1 / 1.58,
            "pixelsPerMicronY": 1 / 1.58,
            "snapshotOffsetXPixel": 50,
            "snapshotOffsetYPixel": 0,
            "orientation": "horizontal",
            "snaked": True,
        }

        update_dcg_requests = [c.request for c in mock_ispyb_conn.calls_for(DCG_RE)]
        assert (
            int(mock_ispyb_conn.match(update_dcg_requests[0], DCG_RE, 2))
            == TEST_DATA_COLLECTION_GROUP_ID
        )
        assert json.loads(update_dcg_requests[0].body)["comments"] == first_comment
        assert (
            int(mock_ispyb_conn.match(update_dcg_requests[1], DCG_RE, 2))
            == TEST_DATA_COLLECTION_GROUP_ID
        )
        assert (
            json.loads(update_dcg_requests[1].body)["comments"]
            == "Diffraction grid scan of 40 by 20 by 10."
        )

    async def test_ispyb_callback_handles_read_hardware_in_run_engine(
        self, RE, mock_ispyb_conn, dummy_rotation_data_collection_group_info
    ):
        callback = GridscanISPyBCallback(
            param_type=GridCommonWithHyperionDetectorParams
        )
        callback._handle_ispyb_hardware_read = MagicMock()
        callback._handle_ispyb_transmission_flux_read = MagicMock()
        callback.ispyb = MagicMock()
        callback.params = MagicMock()
        callback.data_collection_group_info = dummy_rotation_data_collection_group_info

        with init_devices(mock=True):
            test_readable = epics_signal_rw(str, "pv")

        @subs_decorator(callback)
        @run_decorator(
            md={
                "activate_callbacks": ["GridscanISPyBCallback"],
            },
        )
        def test_plan():
            yield from read_hardware_plan(
                [test_readable], DocDescriptorNames.HARDWARE_READ_PRE
            )
            yield from read_hardware_plan(
                [test_readable], DocDescriptorNames.HARDWARE_READ_DURING
            )

        RE(test_plan())

        callback._handle_ispyb_hardware_read.assert_called_once()
        callback._handle_ispyb_transmission_flux_read.assert_called_once()

    @patch(
        "mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback.GridscanISPyBCallback._handle_oav_grid_snapshot_triggered",
    )
    @patch(
        "mx_bluesky.common.external_interaction.ispyb.ispyb_store.StoreInIspyb.update_deposition",
    )
    @patch(
        "mx_bluesky.common.external_interaction.ispyb.ispyb_store.StoreInIspyb.update_data_collection_group_table",
    )
    def test_given_event_doc_before_start_doc_received_then_exception_raised(
        self,
        mock_update_data_collection_group_table,
        mock_update_deposition,
        mock__handle_oav_grid_snapshot_triggered,
        TestEventData,
    ):
        callback = GridscanISPyBCallback(
            param_type=GridCommonWithHyperionDetectorParams
        )
        callback.activity_gated_descriptor(
            TestEventData.test_descriptor_document_oav_snapshot
        )
        callback.ispyb = MagicMock()
        callback.params = MagicMock()
        callback.data_collection_group_info = None
        with pytest.raises(AssertionError) as e:
            callback.activity_gated_event(
                TestEventData.test_event_document_oav_snapshot_xy
            )

        assert "No data collection group info" in str(e.value)

    def test_ispyb_callback_clears_state_after_run_stop(
        self, TestEventData, mock_ispyb_conn
    ):
        callback = GridscanISPyBCallback(
            param_type=GridCommonWithHyperionDetectorParams
        )
        callback.active = True
        callback.start(TestEventData.test_grid_detect_and_gridscan_start_document)  # type: ignore
        callback.descriptor(TestEventData.test_descriptor_document_oav_snapshot)
        callback.event(TestEventData.test_event_document_oav_snapshot_xy)
        callback.event(TestEventData.test_event_document_oav_snapshot_xz)
        callback.start(TestEventData.test_gridscan_outer_start_document)  # type: ignore
        callback.start(TestEventData.test_do_fgs_start_document)  # type: ignore
        callback.descriptor(TestEventData.test_descriptor_document_pre_data_collection)  # type: ignore
        callback.event(TestEventData.test_event_document_pre_data_collection)
        callback.descriptor(TestEventData.test_descriptor_document_zocalo_hardware)
        callback.event(TestEventData.test_event_document_zocalo_hardware)
        callback.descriptor(
            TestEventData.test_descriptor_document_during_data_collection  # type: ignore
        )
        assert callback._grid_plane_to_id_map
        callback.stop(TestEventData.test_do_fgs_stop_document)
        callback.stop(TestEventData.test_gridscan_outer_stop_document)  # type: ignore
        callback.stop(TestEventData.test_grid_detect_and_gridscan_stop_document)
        assert not callback._grid_plane_to_id_map


@pytest.mark.parametrize(
    "omega, expected_plane",
    [
        [0, GridscanPlane.OMEGA_XY],
        [180, GridscanPlane.OMEGA_XY],
        [-180, GridscanPlane.OMEGA_XY],
        [540, GridscanPlane.OMEGA_XY],
        [90, GridscanPlane.OMEGA_XZ],
        [-90, GridscanPlane.OMEGA_XZ],
        [270, GridscanPlane.OMEGA_XZ],
        [-270, GridscanPlane.OMEGA_XZ],
        [0.999, GridscanPlane.OMEGA_XY],
        [-0.999, GridscanPlane.OMEGA_XY],
        [1.001, AssertionError],
        [-1.001, AssertionError],
        [91.001, AssertionError],
        [90.999, GridscanPlane.OMEGA_XZ],
        [89.999, GridscanPlane.OMEGA_XZ],
    ],
)
def test_smargon_omega_to_xyxz_plane(omega, expected_plane):
    expects_exception = not (isinstance(expected_plane, GridscanPlane))
    raises_or_not = (
        pytest.raises(expected_plane) if expects_exception else (nullcontext())
    )
    with raises_or_not:
        plane = _smargon_omega_to_xyxz_plane(omega)
        assert expects_exception or plane == expected_plane
