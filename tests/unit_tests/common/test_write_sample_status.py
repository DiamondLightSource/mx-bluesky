from unittest.mock import MagicMock, patch

import pytest
from bluesky.run_engine import RunEngine

from mx_bluesky.common.external_interaction.ispyb.exp_eye_store import BLSampleStatus
from mx_bluesky.common.plans.write_sample_status import (
    SampleStatusExceptionType,
    deposit_loaded_sample,
    deposit_sample_error,
)
from mx_bluesky.common.utils.exceptions import SampleException

TEST_SAMPLE_ID = 123456


@pytest.mark.parametrize(
    "exception_type, expected_sample_status, expected_raised_exception",
    [
        [
            SampleStatusExceptionType.BEAMLINE,
            BLSampleStatus.ERROR_BEAMLINE,
            AssertionError,
        ],
        [
            SampleStatusExceptionType.SAMPLE,
            BLSampleStatus.ERROR_SAMPLE,
            SampleException,
        ],
    ],
)
def test_depositing_sample_error_with_sample_or_beamline_exception(
    RE: RunEngine,
    exception_type: SampleStatusExceptionType,
    expected_sample_status: BLSampleStatus,
    expected_raised_exception: type,
):
    mock_expeye = MagicMock()
    with (
        patch(
            "mx_bluesky.common.external_interaction.callbacks.sample_handling.sample_handling_callback"
            ".ExpeyeInteraction",
            return_value=mock_expeye,
        ),
        pytest.raises(expected_raised_exception),
    ):
        RE(deposit_sample_error(exception_type, TEST_SAMPLE_ID))
    mock_expeye.update_sample_status.assert_called_once_with(
        TEST_SAMPLE_ID, expected_sample_status
    )


def test_depositing_sample_loaded(
    RE: RunEngine,
):
    mock_expeye = MagicMock()
    with patch(
        "mx_bluesky.common.external_interaction.callbacks.sample_handling.sample_handling_callback"
        ".ExpeyeInteraction",
        return_value=mock_expeye,
    ):
        RE(deposit_loaded_sample(TEST_SAMPLE_ID))
        mock_expeye.update_sample_status.assert_called_once_with(
            TEST_SAMPLE_ID, BLSampleStatus.LOADED
        )
