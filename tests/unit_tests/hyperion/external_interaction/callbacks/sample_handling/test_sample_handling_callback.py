from unittest.mock import MagicMock, patch

import bluesky.preprocessors as bpp
import pytest
from bluesky.preprocessors import run_decorator
from bluesky.run_engine import RunEngine

from mx_bluesky.common.external_interaction.callbacks.sample_handling.sample_handling_callback import (
    SampleHandlingCallback,
)
from mx_bluesky.common.external_interaction.ispyb.exp_eye_store import BLSampleStatus
from mx_bluesky.common.utils.exceptions import (
    CrystalNotFoundException,
    SampleException,
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


def plan_for_sample_id(sample_id):
    def plan_with_exception():
        yield from []
        raise SampleException(f"Test exception for sample_id {sample_id}")

    yield from bpp.run_wrapper(
        plan_with_exception(),
        md={
            "metadata": {"sample_id": sample_id},
            "activate_callbacks": ["SampleHandlingCallback"],
        },
    )


def plan_with_exception_from_inner_plan():
    @run_decorator(
        md={
            "metadata": {"sample_id": TEST_SAMPLE_ID},
        }
    )
    def inner_plan():
        yield from []
        raise SampleException("Exception from inner plan")

    @run_decorator(
        md={
            "metadata": {"sample_id": TEST_SAMPLE_ID},
            "activate_callbacks": ["SampleHandlingCallback"],
        }
    )
    @bpp.set_run_key_decorator("outer_plan")
    def outer_plan():
        yield from inner_plan()

    yield from outer_plan()


def plan_with_rethrown_exception():
    @run_decorator(
        md={
            "metadata": {"sample_id": TEST_SAMPLE_ID},
        }
    )
    def inner_plan():
        yield from []
        raise AssertionError("Exception from inner plan")

    @run_decorator(
        md={
            "metadata": {"sample_id": TEST_SAMPLE_ID},
            "activate_callbacks": ["SampleHandlingCallback"],
        }
    )
    @bpp.set_run_key_decorator("outer_plan")
    def outer_plan():
        try:
            yield from inner_plan()
        except AssertionError as e:
            raise SampleException("Exception from outer plan") from e

    yield from outer_plan()


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


@patch(
    "mx_bluesky.common.external_interaction.callbacks.sample_handling.sample_handling_callback"
    ".ExpeyeInteraction",
)
def test_sample_handling_callback_resets_sample_id(
    mock_expeye_cls: MagicMock, RE: RunEngine
):
    mock_expeye = mock_expeye_cls.return_value
    callback = SampleHandlingCallback()
    RE.subscribe(callback)

    with pytest.raises(SampleException):
        RE(plan_for_sample_id(TEST_SAMPLE_ID))
    mock_expeye.update_sample_status.assert_called_once_with(
        TEST_SAMPLE_ID, BLSampleStatus.ERROR_SAMPLE
    )
    mock_expeye.reset_mock()

    with pytest.raises(SampleException):
        RE(plan_for_sample_id(TEST_SAMPLE_ID + 1))
    mock_expeye.update_sample_status.assert_called_once_with(
        TEST_SAMPLE_ID + 1, BLSampleStatus.ERROR_SAMPLE
    )


@patch(
    "mx_bluesky.common.external_interaction.callbacks.sample_handling.sample_handling_callback"
    ".ExpeyeInteraction",
)
def test_sample_handling_callback_triggered_only_by_outermost_plan_when_exception_thrown_in_inner_plan(
    mock_expeye_cls: MagicMock, RE: RunEngine
):
    mock_expeye = mock_expeye_cls.return_value
    callback = SampleHandlingCallback()
    RE.subscribe(callback)

    with pytest.raises(SampleException):
        RE(plan_with_exception_from_inner_plan())
    mock_expeye.update_sample_status.assert_called_once_with(
        TEST_SAMPLE_ID, BLSampleStatus.ERROR_SAMPLE
    )


@patch(
    "mx_bluesky.common.external_interaction.callbacks.sample_handling.sample_handling_callback"
    ".ExpeyeInteraction",
)
def test_sample_handling_callback_triggered_only_by_outermost_plan_when_exception_rethrown_from_outermost_plan(
    mock_expeye_cls: MagicMock, RE: RunEngine
):
    mock_expeye = mock_expeye_cls.return_value
    callback = SampleHandlingCallback()
    RE.subscribe(callback)

    with pytest.raises(SampleException):
        RE(plan_with_rethrown_exception())
    mock_expeye.update_sample_status.assert_called_once_with(
        TEST_SAMPLE_ID, BLSampleStatus.ERROR_SAMPLE
    )
