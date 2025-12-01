from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import sleep
from unittest.mock import patch

import pytest
from blueapi.core import BlueskyContext
from bluesky import RunEngine
from bluesky import plan_stubs as bps

from mx_bluesky.hyperion.plan_runner import PlanError, PlanRunner


@pytest.fixture(autouse=True)
def patch_timer_poll_interval():
    with patch(
        "mx_bluesky.hyperion.plan_runner.PlanRunner.EXTERNAL_CALLBACK_POLL_INTERVAL_S",
        0.01,
    ):
        yield


@pytest.fixture()
def patch_timer_expiry():
    with patch(
        "mx_bluesky.hyperion.plan_runner.PlanRunner.EXTERNAL_CALLBACK_WATCHDOG_TIMER_S",
        0.1,
    ):
        yield


def test_external_callbacks_waits_for_external_callback_ping(run_engine: RunEngine):
    runner = PlanRunner(BlueskyContext(run_engine=run_engine), True)
    plan_started = Event()

    def execute_test():
        sleep(0.1)
        assert not plan_started.is_set()
        runner.reset_callback_watchdog_timer()
        plan_started.wait(timeout=0.5)

    def test_plan():
        plan_started.set()
        yield from bps.null()

    with ThreadPoolExecutor(1) as executor:
        fut = executor.submit(execute_test)
        run_engine(runner.execute_plan(test_plan))
        fut.result()


def test_external_callbacks_raises_if_never_started(
    run_engine: RunEngine, patch_timer_expiry
):
    runner = PlanRunner(BlueskyContext(run_engine=run_engine), True)
    plan_started = Event()

    def execute_test():
        sleep(0.1)
        assert not plan_started.is_set()
        plan_started.wait(timeout=0.5)

    def test_plan():
        plan_started.set()
        yield from bps.null()

    with ThreadPoolExecutor(1) as executor:
        fut = executor.submit(execute_test)
        with pytest.raises(PlanError) as exc_info:
            run_engine(runner.execute_plan(test_plan))
        fut.result()

    assert exc_info.value.__cause__.args[0].startswith(  # type: ignore
        "External callbacks not running"
    )


def test_external_callbacks_not_running_raises_exception_for_plan_execution(
    run_engine: RunEngine,
    patch_timer_expiry,
):
    runner = PlanRunner(BlueskyContext(run_engine=run_engine), True)

    def execute_test():
        runner.reset_callback_watchdog_timer()

    def test_plan():
        yield from bps.sleep(0.2)

    with ThreadPoolExecutor(1) as executor:
        fut = executor.submit(execute_test)
        run_engine(runner.execute_plan(test_plan))
        with pytest.raises(PlanError) as exc_info:
            run_engine(runner.execute_plan(test_plan))
        assert exc_info.value.__cause__.args[0].startswith(  # type:ignore
            "External callback watchdog timer expired"
        )
        fut.result()
