from unittest.mock import patch

from bluesky import RunEngine
from bluesky.preprocessors import contingency_decorator, run_decorator

from mx_bluesky.hyperion.external_interaction.callbacks.sample_handling.sample_handling_callback import (
    SampleHandlingCallback,
    exception_interceptor,
)

TEST_SAMPLE_ID = 123456


@run_decorator(md={"sample_id": TEST_SAMPLE_ID})
@contingency_decorator(except_plan=exception_interceptor, auto_raise=True)
def plan_with_general_exception():
    yield from []
    raise AssertionError("Test failure")


def test_sample_handling_callback_intercepts_general_exception(RE: RunEngine):
    callback = SampleHandlingCallback()
    RE.subscribe(callback)

    with patch.object(callback, "_record_exception") as record_exception:
        RE(plan_with_general_exception())

        record_exception.assert_called_once_with("AssertionError")
