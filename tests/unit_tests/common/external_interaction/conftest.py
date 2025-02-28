from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
import pytest
from bluesky.run_engine import RunEngine
from ophyd_async.sim import SimMotor

from mx_bluesky.common.external_interaction.callbacks.common.plan_reactive_callback import (
    PlanReactiveCallback,
)


class MockReactiveCallback(PlanReactiveCallback):
    activity_gated_start: MagicMock
    activity_gated_descriptor: MagicMock
    activity_gated_event: MagicMock
    activity_gated_stop: MagicMock

    def __init__(self, *, emit: Callable[..., Any] | None = None) -> None:
        super().__init__(MagicMock(), emit=emit)
        self.activity_gated_start = MagicMock(name="activity_gated_start")  # type: ignore
        self.activity_gated_descriptor = MagicMock(name="activity_gated_descriptor")  # type: ignore
        self.activity_gated_event = MagicMock(name="activity_gated_event")  # type: ignore
        self.activity_gated_stop = MagicMock(name="activity_gated_stop")  # type: ignore


@pytest.fixture
def mocked_test_callback():
    t = MockReactiveCallback()
    return t


@pytest.fixture
def RE_with_mock_callback(mocked_test_callback):
    RE = RunEngine()
    RE.subscribe(mocked_test_callback)
    yield RE, mocked_test_callback


def get_test_plan(callback_name):
    s = SimMotor(name="fake_signal")

    @bpp.run_decorator(md={"activate_callbacks": [callback_name]})
    def test_plan():
        yield from bps.create()
        yield from bps.read(s)
        yield from bps.save()

    return test_plan, s
