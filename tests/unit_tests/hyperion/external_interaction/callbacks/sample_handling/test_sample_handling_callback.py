from unittest.mock import patch

import pytest
from bluesky import RunEngine
from bluesky.preprocessors import contingency_decorator, run_decorator

from mx_bluesky.hyperion.external_interaction.callbacks.sample_handling.sample_handling_callback import (
    SampleHandlingCallback,
    exception_handling_decorator,
)

TEST_SAMPLE_ID = 123456


@run_decorator(md={"metadata": {"sample_id": TEST_SAMPLE_ID},
                   "activate_callbacks": ["SampleHandlingCallback"]})
@exception_handling_decorator()
def plan_with_general_exception():
    yield from []
    raise AssertionError("Test failure")

@exception_handling_decorator()
@run_decorator(md={"metadata": {"sample_id": TEST_SAMPLE_ID},
                   "activate_callbacks": ["SampleHandlingCallback"]})
def plan_with_normal_completion():
    yield from []


def test_sample_handling_callback_intercepts_general_exception(RE: RunEngine):
    callback = SampleHandlingCallback()
    RE.subscribe(callback)

    with (patch.object(callback, "_record_exception") as record_exception,
        pytest.raises(AssertionError)):
        RE(plan_with_general_exception())

    record_exception.assert_called_once_with("AssertionError")


def test_sample_handling_callback_closes_run_normally(RE: RunEngine):
    callback = SampleHandlingCallback()
    RE.subscribe(callback)

    with (patch.object(callback, "_record_exception") as record_exception,
        ):
        RE(plan_with_normal_completion())

    record_exception.assert_not_called()
