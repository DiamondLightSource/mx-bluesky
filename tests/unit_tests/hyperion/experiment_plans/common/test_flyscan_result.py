import pytest
from tests.unit_tests.hyperion.experiment_plans.conftest import (
    FLYSCAN_RESULT_HIGH,
    FLYSCAN_RESULT_LOW,
    FLYSCAN_RESULT_MED,
)

from mx_bluesky.common.xrc_result import (
    top_n_by_max_count,
)


@pytest.mark.parametrize(
    "input_sequence, expected_sequence, n",
    [
        [
            [FLYSCAN_RESULT_LOW, FLYSCAN_RESULT_MED, FLYSCAN_RESULT_HIGH],
            [FLYSCAN_RESULT_HIGH, FLYSCAN_RESULT_MED],
            2,
        ],
        [[FLYSCAN_RESULT_LOW], [FLYSCAN_RESULT_LOW], 2],
    ],
)
def test_top_n_by_max_count(input_sequence, expected_sequence, n):
    actual_sequence = top_n_by_max_count(input_sequence, n)
    assert actual_sequence == expected_sequence
