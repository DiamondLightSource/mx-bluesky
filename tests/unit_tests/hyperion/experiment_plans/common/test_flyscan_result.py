import pytest

from mx_bluesky.common.xrc_result import (
    top_n_by_max_count,
    top_n_by_max_count_for_each_sample,
)
from tests.unit_tests.hyperion.experiment_plans.conftest import (
    FLYSCAN_RESULT_HIGH,
    FLYSCAN_RESULT_LOW,
    FLYSCAN_RESULT_MED,
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


@pytest.mark.parametrize(
    "input_sequence, expected_sequence, n",
    [
        [
            [FLYSCAN_RESULT_LOW, FLYSCAN_RESULT_MED, FLYSCAN_RESULT_HIGH],
            [FLYSCAN_RESULT_MED, FLYSCAN_RESULT_HIGH],
            1,
        ],
        [
            [FLYSCAN_RESULT_LOW, FLYSCAN_RESULT_MED, FLYSCAN_RESULT_HIGH],
            [FLYSCAN_RESULT_LOW, FLYSCAN_RESULT_MED, FLYSCAN_RESULT_HIGH],
            2,
        ],
        [
            [FLYSCAN_RESULT_MED, FLYSCAN_RESULT_MED, FLYSCAN_RESULT_LOW],
            [FLYSCAN_RESULT_MED, FLYSCAN_RESULT_MED],
            2,
        ],
    ],
)
def test_top_n_by_max_count_for_each_sample(input_sequence, expected_sequence, n):
    actual_sequence = top_n_by_max_count_for_each_sample(input_sequence, n)
    # Assert lists are equal, order is not relevant
    assert len(actual_sequence) == len(expected_sequence)
    for result in expected_sequence:
        assert result in actual_sequence
