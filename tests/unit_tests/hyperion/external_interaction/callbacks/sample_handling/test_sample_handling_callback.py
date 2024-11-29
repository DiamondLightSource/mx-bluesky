from unittest.mock import MagicMock, patch

import pytest
from bluesky.preprocessors import run_decorator
from bluesky.run_engine import RunEngine

from mx_bluesky.hyperion.exceptions import SampleException
from mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan import (
    CrystalNotFoundException,
)
from mx_bluesky.hyperion.external_interaction.callbacks.sample_handling.sample_handling_callback import (
    SampleHandlingCallback,
    sample_handling_callback_decorator,
)
from mx_bluesky.hyperion.external_interaction.ispyb.exp_eye_store import BLSampleStatus

TEST_SAMPLE_ID = 123456


@run_decorator(
    md={
        "metadata": {"sample_id": TEST_SAMPLE_ID},
        "activate_callbacks": ["SampleHandlingCallback"],
    }
)
@sample_handling_callback_decorator()
def plan_with_general_exception(exception_type: type):
    yield from []
    raise exception_type("Test failure")


@run_decorator(
    md={
        "metadata": {"sample_id": TEST_SAMPLE_ID},
        "activate_callbacks": ["SampleHandlingCallback"],
    }
)
@sample_handling_callback_decorator()
def plan_with_normal_completion():
    yield from []


@pytest.mark.parametrize(
    "exception_type, expected_sample_status",
    [
        [AssertionError, BLSampleStatus.ERROR_BEAMLINE],
        [SampleException, BLSampleStatus.ERROR_SAMPLE],
        [CrystalNotFoundException, BLSampleStatus.ERROR_SAMPLE],
    ],
)
def test_sample_handling_callback_intercepts_general_exception(
    RE: RunEngine, exception_type: type, expected_sample_status: BLSampleStatus
):
    callback = SampleHandlingCallback()
    RE.subscribe(callback)

    mock_expeye = MagicMock()
    with (
        patch(
            "mx_bluesky.hyperion.external_interaction.callbacks.sample_handling.sample_handling_callback"
            ".ExpeyeInteraction",
            return_value=mock_expeye,
        ),
        pytest.raises(exception_type),
    ):
        RE(plan_with_general_exception(exception_type))
    mock_expeye.update_sample_status.assert_called_once_with(
        TEST_SAMPLE_ID, expected_sample_status
    )


def test_sample_handling_callback_closes_run_normally(RE: RunEngine):
    callback = SampleHandlingCallback()
    RE.subscribe(callback)

    with (
        patch.object(callback, "_record_exception") as record_exception,
    ):
        RE(plan_with_normal_completion())

    record_exception.assert_not_called()
