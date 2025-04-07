import pytest

from mx_bluesky.hyperion.parameters.constants import CONST
from mx_bluesky.hyperion.parameters.rotation import MultiRotationScan


@pytest.fixture
def test_rotation_start_outer_document(dummy_rotation_params: MultiRotationScan):
    dummy_single_rotation_params = next(dummy_rotation_params.single_rotation_scans)
    return {
        "uid": "d8bee3ee-f614-4e7a-a516-25d6b9e87ef3",
        "subplan_name": CONST.PLAN.ROTATION_OUTER,
        "mx_bluesky_parameters": dummy_single_rotation_params.model_dump_json(),
    }
