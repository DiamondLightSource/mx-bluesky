from unittest.mock import MagicMock, patch

import pytest
from bluesky.preprocessors import run_decorator
from bluesky.run_engine import RunEngine

from mx_bluesky.common.external_interaction.callbacks.sample_handling.sample_handling_callback import (
    SampleHandlingCallback,
)
from mx_bluesky.common.external_interaction.ispyb.exp_eye_store import BLSampleStatus
from mx_bluesky.common.utils.exceptions import SampleException
from mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan import (
    CrystalNotFoundException,
)

TEST_SAMPLE_ID = 123456


@run_decorator(
    md={
        "metadata": {"sample_id": TEST_SAMPLE_ID},
        "activate_callbacks": ["SampleHandlingCallback"],
    }
)
def plan_with_general_exception(exception_type: type, msg: str):
    yield from []
    raise exception_type(msg)


@run_decorator(
    md={
        "metadata": {"sample_id": TEST_SAMPLE_ID},
        "activate_callbacks": ["SampleHandlingCallback"],
    }
)
def plan_with_normal_completion():
    yield from []


@pytest.mark.parametrize(
    "exception_type, expected_sample_status, message",
    [
        [AssertionError, BLSampleStatus.ERROR_BEAMLINE, "Test failure"],
        [SampleException, BLSampleStatus.ERROR_SAMPLE, "Test failure"],
        [CrystalNotFoundException, BLSampleStatus.ERROR_SAMPLE, "Test failure"],
        [AssertionError, BLSampleStatus.ERROR_BEAMLINE, None],
    ],
)
def test_sample_handling_callback_intercepts_general_exception(
    RE: RunEngine,
    exception_type: type,
    expected_sample_status: BLSampleStatus,
    message: str,
):
    callback = SampleHandlingCallback()
    RE.subscribe(callback)

    mock_expeye = MagicMock()
    with (
        patch(
            "mx_bluesky.common.external_interaction.callbacks.sample_handling.sample_handling_callback"
            ".ExpeyeInteraction",
            return_value=mock_expeye,
        ),
        pytest.raises(exception_type),
    ):
        RE(plan_with_general_exception(exception_type, message))
    mock_expeye.update_sample_status.assert_called_once_with(
        TEST_SAMPLE_ID, expected_sample_status
    )


def test_sample_handling_callback_closes_run_normally(RE: RunEngine):
    callback = SampleHandlingCallback()
    RE.subscribe(callback)
    mock_expeye = MagicMock()
    with (
        patch.object(callback, "_record_exception") as record_exception,
        patch(
            "mx_bluesky.common.external_interaction.callbacks.sample_handling.sample_handling_callback"
            ".ExpeyeInteraction",
            return_value=mock_expeye,
        ),
    ):
        RE(plan_with_normal_completion())

    record_exception.assert_not_called()
