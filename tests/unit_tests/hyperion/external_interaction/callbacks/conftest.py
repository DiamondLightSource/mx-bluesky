import pytest

from mx_bluesky.hyperion.parameters.constants import CONST
from mx_bluesky.hyperion.parameters.rotation import RotationScan

_UID_ROTATION_OUTER = "d8bee3ee-f614-4e7a-a516-25d6b9e87ef3"


@pytest.fixture
def test_rotation_start_outer_document(dummy_rotation_params: RotationScan):
    dummy_single_rotation_params = next(dummy_rotation_params.single_rotation_scans)
    return {
        "uid": _UID_ROTATION_OUTER,
        "subplan_name": CONST.PLAN.ROTATION_OUTER,
        "mx_bluesky_parameters": dummy_single_rotation_params.model_dump_json(),
    }


@pytest.fixture
def test_rotation_stop_outer_document():
    return {
        "run_start": _UID_ROTATION_OUTER,
        "time": 1666604300.0310638,
        "uid": "65b2bde5-5740-42d7-9047-e860e06fbe15",
        "exit_status": "Success",
        "reason": "",
    }
