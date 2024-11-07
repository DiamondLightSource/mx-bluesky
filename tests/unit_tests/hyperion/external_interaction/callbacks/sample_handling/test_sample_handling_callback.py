from unittest.mock import patch

import pytest
from bluesky.preprocessors import run_decorator
from bluesky.run_engine import RunEngine

from mx_bluesky.hyperion.external_interaction.callbacks.sample_handling.sample_handling_callback import (
    SampleHandlingCallback,
    sample_handling_callback_decorator,
)

TEST_SAMPLE_ID = 123456


@run_decorator(
    md={
        "metadata": {"sample_id": TEST_SAMPLE_ID},
        "activate_callbacks": ["SampleHandlingCallback"],
    }
)
@sample_handling_callback_decorator()
def plan_with_general_exception():
    yield from []
    raise AssertionError("Test failure")


@run_decorator(
    md={
        "metadata": {"sample_id": TEST_SAMPLE_ID},
        "activate_callbacks": ["SampleHandlingCallback"],
    }
)
@sample_handling_callback_decorator()
def plan_with_normal_completion():
    yield from []


def test_sample_handling_callback_intercepts_general_exception(RE: RunEngine):
    callback = SampleHandlingCallback()
    RE.subscribe(callback)

    with (
        patch.object(callback, "_record_exception") as record_exception,
        pytest.raises(AssertionError),
    ):
        RE(plan_with_general_exception())

    record_exception.assert_called_once_with("AssertionError")


def test_sample_handling_callback_closes_run_normally(RE: RunEngine):
    callback = SampleHandlingCallback()
    RE.subscribe(callback)

    with (
        patch.object(callback, "_record_exception") as record_exception,
    ):
        RE(plan_with_normal_completion())

    record_exception.assert_not_called()
