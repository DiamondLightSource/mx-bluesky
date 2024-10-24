import pytest
from dodal.devices.aperturescatterguard import ApertureValue
from dodal.devices.synchrotron import SynchrotronMode
from dodal.devices.zocalo.zocalo_results import ZOCALO_READING_PLAN_NAME
from event_model.documents import Event, EventDescriptor, RunStart, RunStop

from mx_bluesky.hyperion.parameters.constants import CONST
from mx_bluesky.hyperion.parameters.gridscan import ThreeDGridScan
from tests.conftest import create_dummy_scan_spec

from .....conftest import default_raw_params, raw_params_from_file
from ...conftest import OavGridSnapshotTestEvents


def dummy_params():
    dummy_params = ThreeDGridScan(**default_raw_params())
    return dummy_params


def dummy_params_2d():
    raw_params = raw_params_from_file(
        "tests/test_data/parameter_json_files/test_gridscan_param_defaults.json"
    )
    raw_params["z_steps"] = 1
    return ThreeDGridScan(**raw_params)


@pytest.fixture
def test_rotation_start_outer_document(dummy_rotation_params):
    return {
        "uid": "d8bee3ee-f614-4e7a-a516-25d6b9e87ef3",
        "subplan_name": CONST.PLAN.ROTATION_OUTER,
        "hyperion_parameters": dummy_rotation_params.model_dump_json(),
    }


class TestData(OavGridSnapshotTestEvents):
    DUMMY_TIME_STRING: str = "1970-01-01 00:00:00"
    GOOD_ISPYB_RUN_STATUS: str = "DataCollection Successful"
    BAD_ISPYB_RUN_STATUS: str = "DataCollection Unsuccessful"
    test_start_document: RunStart = {  # type: ignore
        "uid": "d8bee3ee-f614-4e7a-a516-25d6b9e87ef3",
        "time": 1666604299.6149616,
        "versions": {"ophyd": "1.6.4.post76+g0895f9f", "bluesky": "1.8.3"},
        "scan_id": 1,
        "plan_type": "generator",
        "plan_name": CONST.PLAN.GRIDSCAN_OUTER,
        "subplan_name": CONST.PLAN.GRIDSCAN_OUTER,
        CONST.TRIGGER.ZOCALO: CONST.PLAN.DO_FGS,
        "hyperion_parameters": dummy_params().model_dump_json(),
    }
    test_gridscan3d_start_document: RunStart = {  # type: ignore
        "uid": "d8bee3ee-f614-4e7a-a516-25d6b9e87ef3",
        "time": 1666604299.6149616,
        "versions": {"ophyd": "1.6.4.post76+g0895f9f", "bluesky": "1.8.3"},
        "scan_id": 1,
        "plan_type": "generator",
        "plan_name": "test",
        "subplan_name": CONST.PLAN.GRID_DETECT_AND_DO_GRIDSCAN,
        "hyperion_parameters": dummy_params().model_dump_json(),
    }
    test_gridscan2d_start_document = {
        "uid": "d8bee3ee-f614-4e7a-a516-25d6b9e87ef3",
        "time": 1666604299.6149616,
        "versions": {"ophyd": "1.6.4.post76+g0895f9f", "bluesky": "1.8.3"},
        "scan_id": 1,
        "plan_type": "generator",
        "plan_name": "test",
        "subplan_name": CONST.PLAN.GRID_DETECT_AND_DO_GRIDSCAN,
        "hyperion_parameters": dummy_params_2d().model_dump_json(),
    }
    test_rotation_start_main_document = {
        "uid": "2093c941-ded1-42c4-ab74-ea99980fbbfd",
        "subplan_name": CONST.PLAN.ROTATION_MAIN,
        "zocalo_environment": "dev_artemis",
    }
    test_gridscan_outer_start_document = {
        "uid": "d8bee3ee-f614-4e7a-a516-25d6b9e87ef3",
        "time": 1666604299.6149616,
        "versions": {"ophyd": "1.6.4.post76+g0895f9f", "bluesky": "1.8.3"},
        "scan_id": 1,
        "plan_type": "generator",
        "plan_name": CONST.PLAN.GRIDSCAN_OUTER,
        "subplan_name": CONST.PLAN.GRIDSCAN_OUTER,
        "zocalo_environment": "dev_artemis",
        CONST.TRIGGER.ZOCALO: CONST.PLAN.DO_FGS,
        "hyperion_parameters": dummy_params().model_dump_json(),
    }
    test_rotation_event_document_during_data_collection: Event = {
        "descriptor": "bd45c2e5-2b85-4280-95d7-a9a15800a78b",
        "time": 2666604299.928203,
        "data": {
            "aperture_scatterguard-aperture-x": 15,
            "aperture_scatterguard-aperture-y": 16,
            "aperture_scatterguard-aperture-z": 2,
            "aperture_scatterguard-scatterguard-x": 18,
            "aperture_scatterguard-scatterguard-y": 19,
            "aperture_scatterguard-selected_aperture": ApertureValue.MEDIUM,
            "aperture_scatterguard-radius": 50,
            "attenuator-actual_transmission": 0.98,
            "flux_flux_reading": 9.81,
            "dcm-energy_in_kev": 11.105,
        },
        "timestamps": {"det1": 1666604299.8220396, "det2": 1666604299.8235943},
        "seq_num": 1,
        "uid": "2093c941-ded1-42c4-ab74-ea99980fbbfd",
        "filled": {},
    }
    test_rotation_stop_main_document: RunStop = {
        "run_start": "2093c941-ded1-42c4-ab74-ea99980fbbfd",
        "time": 1666604300.0310638,
        "uid": "65b2bde5-5740-42d7-9047-e860e06fbe15",
        "exit_status": "success",
        "reason": "Test succeeded",
        "num_events": {"fake_ispyb_params": 1, "primary": 1},
    }
    test_run_gridscan_start_document: RunStart = {  # type: ignore
        "uid": "d8bee3ee-f614-4e7a-a516-25d6b9e87ef3",
        "time": 1666604299.6149616,
        "versions": {"ophyd": "1.6.4.post76+g0895f9f", "bluesky": "1.8.3"},
        "scan_id": 1,
        "plan_type": "generator",
        "plan_name": CONST.PLAN.GRIDSCAN_AND_MOVE,
        "subplan_name": CONST.PLAN.GRIDSCAN_MAIN,
    }
    test_do_fgs_start_document: RunStart = {  # type: ignore
        "uid": "d8bee3ee-f614-4e7a-a516-25d6b9e87ef3",
        "time": 1666604299.6149616,
        "versions": {"ophyd": "1.6.4.post76+g0895f9f", "bluesky": "1.8.3"},
        "scan_id": 1,
        "plan_type": "generator",
        "plan_name": CONST.PLAN.GRIDSCAN_AND_MOVE,
        "subplan_name": CONST.PLAN.DO_FGS,
        "scan_points": create_dummy_scan_spec(10, 20, 30),
    }
    test_descriptor_document_oav_rotation_snapshot: EventDescriptor = {
        "uid": "c7d698ce-6d49-4c56-967e-7d081f964573",
        "run_start": "d8bee3ee-f614-4e7a-a516-25d6b9e87ef3",
        "name": CONST.DESCRIPTORS.OAV_ROTATION_SNAPSHOT_TRIGGERED,
    }  # type: ignore
    test_descriptor_document_pre_data_collection: EventDescriptor = {
        "uid": "bd45c2e5-2b85-4280-95d7-a9a15800a78b",
        "run_start": "d8bee3ee-f614-4e7a-a516-25d6b9e87ef3",
        "name": CONST.DESCRIPTORS.HARDWARE_READ_PRE,
    }  # type: ignore
    test_descriptor_document_during_data_collection: EventDescriptor = {
        "uid": "bd45c2e5-2b85-4280-95d7-a9a15800a78b",
        "run_start": "d8bee3ee-f614-4e7a-a516-25d6b9e87ef3",
        "name": CONST.DESCRIPTORS.HARDWARE_READ_DURING,
    }  # type: ignore
    test_descriptor_document_zocalo_hardware: EventDescriptor = {
        "uid": "f082901b-7453-4150-8ae5-c5f98bb34406",
        "run_start": "d8bee3ee-f614-4e7a-a516-25d6b9e87ef3",
        "name": CONST.DESCRIPTORS.ZOCALO_HW_READ,
    }  # type: ignore
    test_event_document_oav_rotation_snapshot: Event = {
        "descriptor": "c7d698ce-6d49-4c56-967e-7d081f964573",
        "time": 1666604299.828203,
        "timestamps": {},
        "seq_num": 1,
        "uid": "32d7c25c-c310-4292-ac78-36ce6509be3d",
        "data": {"oav_snapshot_last_saved_path": "snapshot_0"},
    }
    test_event_document_pre_data_collection: Event = {
        "descriptor": "bd45c2e5-2b85-4280-95d7-a9a15800a78b",
        "time": 1666604299.828203,
        "data": {
            "s4_slit_gaps_xgap": 0.1234,
            "s4_slit_gaps_ygap": 0.2345,
            "synchrotron-synchrotron_mode": SynchrotronMode.USER,
            "undulator-current_gap": 1.234,
            "smargon-x": 0.158435435,
            "smargon-y": 0.023547354,
            "smargon-z": 0.00345684712,
            "dcm-energy_in_kev": 11.105,
        },
        "timestamps": {"det1": 1666604299.8220396, "det2": 1666604299.8235943},
        "seq_num": 1,
        "uid": "29033ecf-e052-43dd-98af-c7cdd62e8173",
        "filled": {},
    }
    test_event_document_during_data_collection: Event = {
        "descriptor": "bd45c2e5-2b85-4280-95d7-a9a15800a78b",
        "time": 2666604299.928203,
        "data": {
            "aperture_scatterguard-aperture-x": 15,
            "aperture_scatterguard-aperture-y": 16,
            "aperture_scatterguard-aperture-z": 2,
            "aperture_scatterguard-scatterguard-x": 18,
            "aperture_scatterguard-scatterguard-y": 19,
            "aperture_scatterguard-selected_aperture": ApertureValue.MEDIUM,
            "aperture_scatterguard-radius": 50,
            "attenuator-actual_transmission": 1,
            "flux_flux_reading": 10,
            "dcm-energy_in_kev": 11.105,
            "eiger_bit_depth": "16",
        },
        "timestamps": {
            "det1": 1666604299.8220396,
            "det2": 1666604299.8235943,
            "eiger_bit_depth": 1666604299.8220396,
        },
        "seq_num": 1,
        "uid": "29033ecf-e052-43dd-98af-c7cdd62e8174",
        "filled": {},
    }
    test_event_document_zocalo_hardware: Event = {
        "uid": "29033ecf-e052-43dd-98af-c7cdd62e8175",
        "time": 1709654583.9770422,
        "data": {"eiger_odin_file_writer_id": "test_path"},
        "timestamps": {"eiger_odin_file_writer_id": 1666604299.8220396},
        "seq_num": 1,
        "filled": {},
        "descriptor": "f082901b-7453-4150-8ae5-c5f98bb34406",
    }
    test_stop_document: RunStop = {
        "run_start": "d8bee3ee-f614-4e7a-a516-25d6b9e87ef3",
        "time": 1666604300.0310638,
        "uid": "65b2bde5-5740-42d7-9047-e860e06fbe15",
        "exit_status": "success",
        "reason": "",
        "num_events": {"fake_ispyb_params": 1, "primary": 1},
    }
    test_run_gridscan_stop_document: RunStop = {
        "run_start": "d8bee3ee-f614-4e7a-a516-25d6b9e87ef3",
        "time": 1666604300.0310638,
        "uid": "65b2bde5-5740-42d7-9047-e860e06fbe15",
        "exit_status": "success",
        "reason": "",
        "num_events": {"fake_ispyb_params": 1, "primary": 1},
    }
    test_do_fgs_gridscan_stop_document: RunStop = {
        "run_start": "d8bee3ee-f614-4e7a-a516-25d6b9e87ef3",
        "time": 1666604300.0310638,
        "uid": "65b2bde5-5740-42d7-9047-e860e06fbe15",
        "exit_status": "success",
        "reason": "",
        "num_events": {"fake_ispyb_params": 1, "primary": 1},
    }
    test_failed_stop_document: RunStop = {
        "run_start": "d8bee3ee-f614-4e7a-a516-25d6b9e87ef3",
        "time": 1666604300.0310638,
        "uid": "65b2bde5-5740-42d7-9047-e860e06fbe15",
        "exit_status": "fail",
        "reason": "could not connect to devices",
        "num_events": {"fake_ispyb_params": 1, "primary": 1},
    }
    test_run_gridscan_failed_stop_document: RunStop = {
        "run_start": "d8bee3ee-f614-4e7a-a516-25d6b9e87ef3",
        "time": 1666604300.0310638,
        "uid": "65b2bde5-5740-42d7-9047-e860e06fbe15",
        "exit_status": "fail",
        "reason": "could not connect to devices",
        "num_events": {"fake_ispyb_params": 1, "primary": 1},
    }
    test_descriptor_document_zocalo_reading: EventDescriptor = {
        "uid": "unique_id_zocalo_reading",
        "run_start": "d8bee3ee-f614-4e7a-a516-25d6b9e87ef3",
        "name": ZOCALO_READING_PLAN_NAME,
    }  # type:ignore
    test_zocalo_reading_event: Event = {
        "descriptor": "unique_id_zocalo_reading",
        "data": {"zocalo-results": []},
    }  # type:ignore
