import pytest
from bluesky import RunEngine
from bluesky.plan_stubs import null

from mx_bluesky.common.utils.exceptions import (
    WarningError,
    catch_exception_and_warn,
)


class _TestError(Exception):
    pass


def dummy_plan():
    yield from null()
    raise _TestError


def test_catch_exception_and_warn_correctly_raises_warning_exception(
    run_engine: RunEngine,
):
    with pytest.raises(WarningError):
        run_engine(catch_exception_and_warn(_TestError, dummy_plan))


def test_catch_exception_and_warn_correctly_raises_original_exception(
    run_engine: RunEngine,
):
    with pytest.raises(_TestError):
        run_engine(catch_exception_and_warn(ValueError, dummy_plan))
