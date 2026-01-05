from concurrent.futures import Executor
from threading import Event
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from blueapi.client.event_bus import BlueskyStreamingError
from blueapi.core import BlueskyContext
from blueapi.service.model import TaskRequest
from bluesky import RunEngine, RunEngineInterrupted
from bluesky import plan_stubs as bps

from mx_bluesky.common.parameters.components import (
    MxBlueskyParameters,
    get_param_version,
)
from mx_bluesky.common.parameters.constants import Status
from mx_bluesky.hyperion.parameters.components import UDCCleanup, UDCDefaultState, Wait
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect
from mx_bluesky.hyperion.plan_runner import PlanError
from mx_bluesky.hyperion.supervisor import SupervisorRunner

TEST_VISIT = "cm12345-67"


@pytest.fixture
def mock_bluesky_context(run_engine: RunEngine):
    return BlueskyContext(run_engine=run_engine)


@pytest.fixture(autouse=True)
def mock_blueapi_client():
    with patch(
        "mx_bluesky.hyperion.supervisor._supervisor.BlueapiClient"
    ) as mock_class:
        yield mock_class.from_config.return_value


@pytest.fixture
def blueapi_config():
    return MagicMock()


@pytest.fixture
def runner(mock_bluesky_context, blueapi_config):
    runner = SupervisorRunner(mock_bluesky_context, blueapi_config, True)
    with patch.object(runner, "check_external_callbacks_are_alive"):
        yield runner


def test_decode_and_execute_load_centre_collect(
    mock_blueapi_client: MagicMock, runner: SupervisorRunner, load_centre_collect_params
):
    runner.context.run_engine(
        runner.decode_and_execute(TEST_VISIT, [load_centre_collect_params])
    )

    mock_blueapi_client.run_task.assert_called_once_with(
        TaskRequest(
            name="load_centre_collect",
            params={"parameters": load_centre_collect_params},
            instrument_session=TEST_VISIT,
        )
    )


def test_decode_and_execute_wait(
    mock_blueapi_client: MagicMock, runner: SupervisorRunner
):
    mock_sleep = AsyncMock()
    runner.context.run_engine.register_command("sleep", mock_sleep)
    try:
        runner.context.run_engine(
            runner.decode_and_execute(
                TEST_VISIT,
                [
                    Wait.model_validate(
                        {
                            "parameter_model_version": get_param_version(),
                            "duration_s": 10,
                        }
                    )
                ],
            )
        )
    finally:
        runner.context.run_engine.register_command(
            "sleep", runner.context.run_engine._sleep
        )

    mock_blueapi_client.run_task.assert_not_called()
    mock_sleep.assert_awaited_once()


def test_decode_and_execute_default_state(
    mock_blueapi_client: MagicMock, runner: SupervisorRunner
):
    runner.context.run_engine(
        runner.decode_and_execute(
            TEST_VISIT,
            [
                UDCDefaultState.model_validate(
                    {"parameter_model_version": get_param_version()}
                )
            ],
        )
    )

    mock_blueapi_client.run_task.assert_called_once_with(
        TaskRequest(
            name="move_to_udc_default_state", params={}, instrument_session=TEST_VISIT
        )
    )


def test_decode_and_execute_udc_cleanup(
    mock_blueapi_client: MagicMock, runner: SupervisorRunner
):
    runner.context.run_engine(
        runner.decode_and_execute(
            TEST_VISIT,
            [
                UDCCleanup.model_validate(
                    {"parameter_model_version": get_param_version()}
                )
            ],
        )
    )

    mock_blueapi_client.run_task.assert_called_once_with(
        TaskRequest(
            name="clean_up_udc",
            params={"visit": TEST_VISIT},
            instrument_session=TEST_VISIT,
        )
    )


def test_current_status_set_to_busy_during_execution(
    mock_blueapi_client: MagicMock, runner: SupervisorRunner, executor: Executor
):
    task_executing = Event()
    check_complete = Event()

    def check_busy():
        task_executing.wait(timeout=1)
        assert runner.current_status == Status.BUSY
        check_complete.set()

    def wait_for_check(_):
        task_executing.set()
        check_complete.wait(1)

    mock_blueapi_client.run_task.side_effect = wait_for_check

    fut = executor.submit(check_busy)
    try:
        assert runner.current_status == Status.IDLE
        runner.context.run_engine(
            runner.decode_and_execute(
                TEST_VISIT,
                [
                    UDCDefaultState.model_validate(
                        {"parameter_model_version": get_param_version()}
                    )
                ],
            )
        )
    finally:
        fut.result(1)


def test_current_status_set_to_failed_on_exception_and_raise_plan_error(
    mock_blueapi_client: MagicMock, runner: SupervisorRunner
):
    mock_blueapi_client.run_task.side_effect = BlueskyStreamingError(
        "Simulated exception"
    )

    with pytest.raises(PlanError, match="Exception raised.*: Simulated exception"):
        runner.context.run_engine(
            runner.decode_and_execute(
                TEST_VISIT,
                [
                    UDCDefaultState.model_validate(
                        {"parameter_model_version": get_param_version()}
                    )
                ],
            )
        )
    assert runner.current_status == Status.FAILED


def test_is_connected_queries_blueapi_client(
    runner: SupervisorRunner, mock_blueapi_client: MagicMock
):
    assert runner.is_connected()
    mock_blueapi_client.get_state.assert_called_once()


def test_is_connected_returns_false_on_exception(
    runner: SupervisorRunner, mock_blueapi_client: MagicMock
):
    mock_blueapi_client.get_state.side_effect = RuntimeError("Simulated exception")
    assert not runner.is_connected()


def test_shutdown_sends_abort_to_run_engine_when_idle(
    runner: SupervisorRunner, executor: Executor
):
    runner.run_engine = MagicMock(spec=RunEngine)

    def request_shutdown():
        runner.shutdown()

    fut = executor.submit(request_shutdown)

    fut.result(1)
    runner.run_engine.abort.assert_called_once()


def test_shutdown_sends_abort_to_blueapi_client_when_running_then_aborts(
    runner: SupervisorRunner, executor: Executor
):
    task_running = Event()
    remote_abort_requested = Event()

    def request_shutdown():
        task_running.wait(1)
        runner.shutdown()

    def mock_run_task(_):
        task_running.set()
        remote_abort_requested.wait(1)
        raise BlueskyStreamingError("Simulated abort exception")

    def mock_baton_handler_loop():
        yield from runner.decode_and_execute(
            TEST_VISIT,
            [
                UDCDefaultState.model_validate(
                    {"parameter_model_version": get_param_version()}
                )
            ],
        )
        while True:
            yield from bps.sleep(0.1)

    runner.blueapi_client.run_task.side_effect = mock_run_task  # type: ignore
    runner.blueapi_client.abort.side_effect = remote_abort_requested.set  # type: ignore

    fut = executor.submit(request_shutdown)
    try:
        with pytest.raises(RunEngineInterrupted):
            runner.context.run_engine(mock_baton_handler_loop())
    finally:
        fut.result(1)


def test_exception_during_callback_check_raises_plan_error(
    runner: SupervisorRunner, load_centre_collect_params: LoadCentreCollect
):
    with patch.object(
        runner,
        "check_external_callbacks_are_alive",
        side_effect=RuntimeError("Simulated exception"),
    ):
        with pytest.raises(PlanError, match="Exception raised.*: Simulated exception"):
            runner.context.run_engine(
                runner.decode_and_execute(TEST_VISIT, [load_centre_collect_params])
            )


def test_unrecognised_instruction_raises_assertion_error(runner: SupervisorRunner):
    with pytest.raises(AssertionError, match="Unsupported instruction"):
        runner.context.run_engine(
            runner.decode_and_execute(
                TEST_VISIT,
                [
                    MxBlueskyParameters.model_validate(
                        {"parameter_model_version": get_param_version()}
                    )
                ],
            )
        )
