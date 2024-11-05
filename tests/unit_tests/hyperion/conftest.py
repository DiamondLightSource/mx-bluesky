from pathlib import Path
from unittest.mock import patch

import pytest
from event_model import Event, EventDescriptor

from mx_bluesky.hyperion.parameters.constants import CONST

BANNED_PATHS = [Path("/dls"), Path("/dls_sw")]


@pytest.fixture(autouse=True)
def patch_open_to_prevent_dls_reads_in_tests():
    unpatched_open = open

    def patched_open(*args, **kwargs):
        requested_path = Path(args[0])
        if requested_path.is_absolute():
            for p in BANNED_PATHS:
                assert not requested_path.is_relative_to(
                    p
                ), f"Attempt to open {requested_path} from inside a unit test"
        return unpatched_open(*args, **kwargs)

    with patch("builtins.open", side_effect=patched_open):
        yield []


class OavGridSnapshotTestEvents:
    test_descriptor_document_oav_snapshot: EventDescriptor = {
        "uid": "b5ba4aec-de49-4970-81a4-b4a847391d34",
        "run_start": "d8bee3ee-f614-4e7a-a516-25d6b9e87ef3",
        "name": CONST.DESCRIPTORS.OAV_GRID_SNAPSHOT_TRIGGERED,
    }  # type: ignore
    test_event_document_oav_snapshot_xy: Event = {
        "descriptor": "b5ba4aec-de49-4970-81a4-b4a847391d34",
        "time": 1666604299.828203,
        "timestamps": {},
        "seq_num": 1,
        "uid": "29033ecf-e052-43dd-98af-c7cdd62e8174",
        "data": {
            "oav-grid_snapshot-top_left_x": 50,
            "oav-grid_snapshot-top_left_y": 100,
            "oav-grid_snapshot-num_boxes_x": 40,
            "oav-grid_snapshot-num_boxes_y": 20,
            "oav-microns_per_pixel_x": 1.58,
            "oav-microns_per_pixel_y": 1.58,
            "oav-beam_centre_i": 517,
            "oav-beam_centre_j": 350,
            "oav-grid_snapshot-box_width": 0.1 * 1000 / 1.25,  # size in pixels
            "oav-grid_snapshot-last_path_full_overlay": "test_1_y",
            "oav-grid_snapshot-last_path_outer": "test_2_y",
            "oav-grid_snapshot-last_saved_path": "test_3_y",
            "smargon-omega": 0,
            "smargon-x": 0,
            "smargon-y": 0,
            "smargon-z": 0,
        },
    }
    test_event_document_oav_snapshot_xz: Event = {
        "descriptor": "b5ba4aec-de49-4970-81a4-b4a847391d34",
        "time": 1666604299.828203,
        "timestamps": {},
        "seq_num": 1,
        "uid": "29033ecf-e052-43dd-98af-c7cdd62e8174",
        "data": {
            "oav-grid_snapshot-top_left_x": 50,
            "oav-grid_snapshot-top_left_y": 0,
            "oav-grid_snapshot-num_boxes_x": 40,
            "oav-grid_snapshot-num_boxes_y": 10,
            "oav-grid_snapshot-box_width": 0.1 * 1000 / 1.25,  # size in pixels
            "oav-grid_snapshot-last_path_full_overlay": "test_1_z",
            "oav-grid_snapshot-last_path_outer": "test_2_z",
            "oav-grid_snapshot-last_saved_path": "test_3_z",
            "oav-microns_per_pixel_x": 1.58,
            "oav-microns_per_pixel_y": 1.58,
            "oav-beam_centre_i": 517,
            "oav-beam_centre_j": 350,
            "smargon-omega": -90,
            "smargon-x": 0,
            "smargon-y": 0,
            "smargon-z": 0,
        },
    }
