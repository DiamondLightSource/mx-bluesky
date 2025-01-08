from unittest.mock import MagicMock, patch

import pytest
from bluesky.run_engine import RunEngine

from mx_bluesky.common.external_interaction.ispyb.exp_eye_store import BLSampleStatus
from mx_bluesky.common.plans.write_sample_status import (
    deposit_loaded_sample,
    deposit_sample_error,
)
from mx_bluesky.common.utils.exceptions import SampleException
from mx_bluesky.hyperion.external_interaction.callbacks.sample_handling.sample_handling_callback import (
    SampleHandlingCallback,
)

TEST_SAMPLE_ID = 123456


@pytest.mark.parametrize(
    "exception_type, expected_sample_status, expected_raised_exception",
    [
        ["Beamline", BLSampleStatus.ERROR_BEAMLINE, AssertionError],
        ["Sample", BLSampleStatus.ERROR_SAMPLE, SampleException],
    ],
)
def test_depositing_sample_error_with_sample_or_beamline_exception(
    RE: RunEngine,
    exception_type: str,
    expected_sample_status: BLSampleStatus,
    expected_raised_exception: type,
):
    sample_handling_callback = SampleHandlingCallback()
    RE.subscribe(sample_handling_callback)

    mock_expeye = MagicMock()
    with (
        patch(
            "mx_bluesky.hyperion.external_interaction.callbacks.sample_handling.sample_handling_callback"
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
    sample_handling_callback = SampleHandlingCallback()
    RE.subscribe(sample_handling_callback)

    mock_expeye = MagicMock()
    with patch(
        "mx_bluesky.hyperion.external_interaction.callbacks.sample_handling.sample_handling_callback"
        ".ExpeyeInteraction",
        return_value=mock_expeye,
    ):
        RE(deposit_loaded_sample(TEST_SAMPLE_ID))
        mock_expeye.update_sample_status.assert_called_once_with(
            TEST_SAMPLE_ID, BLSampleStatus.LOADED
        )
