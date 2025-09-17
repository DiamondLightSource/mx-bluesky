from asyncio import Event
from unittest.mock import MagicMock, patch

import bluesky.plan_stubs as bps
import pytest
from blueapi.core import BlueskyContext
from bluesky import RunEngine
from bluesky.utils import MsgGenerator

from mx_bluesky.common.parameters.constants import Actions, Status
from mx_bluesky.common.utils.exceptions import WarningException
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect
from mx_bluesky.hyperion.runner import Command, GDARunner
from unit_tests.hyperion.conftest import launch_test_in_runner_event_loop


@pytest.fixture
def context(RE: RunEngine) -> BlueskyContext:
    return MagicMock(run_engine=RE)


@pytest.fixture
def mock_composite():
    return MagicMock()


@pytest.fixture
def runner(context, mock_composite):
    with patch.dict(
        "mx_bluesky.hyperion.experiment_plans.experiment_registry.PLAN_REGISTRY",
        {
            "load_centre_collect_full": {
                "setup": mock_composite,
                "param_type": LoadCentreCollect,
            }
        },
    ):
        yield GDARunner(context)


def test_wait_on_queue_processes_start_command(
    runner: GDARunner, load_centre_collect_params: LoadCentreCollect, mock_composite
):
    mock_plan = MagicMock()
    runner.start(mock_plan, load_centre_collect_params, "load_centre_collect_full")
    runner._command_queue.put(Command(action=Actions.SHUTDOWN))
    runner.wait_on_queue()
    mock_plan.assert_called_once_with(
        mock_composite.return_value, load_centre_collect_params
    )
    assert runner.current_status.status == Status.IDLE.value


def test_wait_on_queue_intercepts_warning_exception_reports_failed_status(
    runner: GDARunner, load_centre_collect_params: LoadCentreCollect, mock_composite
):
    mock_plan = MagicMock(side_effect=WarningException("Mock warning"))
    runner.start(mock_plan, load_centre_collect_params, "load_centre_collect_full")
    runner._command_queue.put(Command(action=Actions.SHUTDOWN))
    runner.wait_on_queue()
    mock_plan.assert_called_once_with(
        mock_composite.return_value, load_centre_collect_params
    )
    assert runner.current_status.status == Status.FAILED.value


def test_wait_on_queue_intercepts_beamline_exception_reports_failed_status(
    runner: GDARunner, load_centre_collect_params: LoadCentreCollect, mock_composite
):
    mock_plan = MagicMock(side_effect=RuntimeError("Mock error"))
    runner.start(mock_plan, load_centre_collect_params, "load_centre_collect_full")
    runner._command_queue.put(Command(action=Actions.SHUTDOWN))
    runner.wait_on_queue()
    mock_plan.assert_called_once_with(
        mock_composite.return_value, load_centre_collect_params
    )
    assert runner.current_status.status == Status.FAILED.value


def test_wait_on_queue_stop_interrupts_running_plan(
    runner: GDARunner,
    load_centre_collect_params: LoadCentreCollect,
    mock_composite,
    executor,
):
    wait_for_plan_start = Event()

    def mock_plan(composite, params) -> MsgGenerator:
        wait_for_plan_start.set()
        yield from bps.sleep(10.0)

    async def wait_and_then_stop():
        await wait_for_plan_start.wait()
        runner.stop()

    runner.start(mock_plan, load_centre_collect_params, "load_centre_collect_full")
    runner._command_queue.put(Command(action=Actions.SHUTDOWN))
    stop_task = launch_test_in_runner_event_loop(wait_and_then_stop, runner, executor)
    runner.wait_on_queue()
    assert stop_task.done()
