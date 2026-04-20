import re
from collections.abc import Callable, Generator
from typing import TypeVar

from bluesky.plan_stubs import null
from bluesky.preprocessors import contingency_wrapper
from bluesky.utils import Msg


class WarningException(Exception):
    """An exception used when we want to warn GDA of a
    problem but continue with UDC anyway"""

    pass


class ISPyBDepositionNotMade(Exception):
    """Raised when the ISPyB or Zocalo callbacks can't access ISPyB deposition numbers."""

    pass


class SampleException(WarningException):
    """An exception which identifies an issue relating to the sample."""

    def __str__(self):
        class_name = type(self).__name__
        return f"[{class_name}]: {super().__str__()}"

    @classmethod
    def type_and_message_from_reason(cls, reason: str) -> tuple[str, str]:
        match = re.match(r"\[(\S*)?]: (.*)", reason)
        return (match.group(1), match.group(2)) if match else (None, None)


T = TypeVar("T")


class CrystalNotFoundException(SampleException):
    """Raised if grid detection completed normally but no crystal was found."""

    def __init__(self, *args):
        super().__init__("Diffraction not found, skipping sample.")


def catch_exception_and_warn(
    exception_to_catch: type[Exception],
    func: Callable[..., Generator[Msg, None, T]],
    *args,
    **kwargs,
) -> Generator[Msg, None, T]:
    """A plan wrapper to catch a specific exception and instead raise a WarningException,
    so that UDC is not halted

    Example usage:

    'def plan_which_can_raise_exception_a(*args, **kwargs):
        ...
    yield from catch_exception_and_warn(ExceptionA, plan_which_can_raise_exception_a, **args, **kwargs)'

    This will catch ExceptionA raised by the plan and instead raise a WarningException
    """

    def warn_if_exception_matches(exception: Exception):
        if isinstance(exception, exception_to_catch):
            raise SampleException(str(exception)) from exception
        yield from null()

    return (
        yield from contingency_wrapper(
            func(*args, **kwargs),
            except_plan=warn_if_exception_matches,
        )
    )
