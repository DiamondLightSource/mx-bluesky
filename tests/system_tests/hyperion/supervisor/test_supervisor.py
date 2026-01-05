import subprocess
import time
from concurrent.futures.thread import ThreadPoolExecutor
from functools import partial
from os import environ, getcwd
from pathlib import Path
from threading import Event
from time import sleep

import pytest
from blueapi.client.event_bus import AnyEvent, EventBusClient
from blueapi.config import ApplicationConfig, ConfigLoader
from blueapi.core import BlueskyContext, DataEvent
from blueapi.worker import WorkerEvent, WorkerState
from bluesky import RunEngine, RunEngineInterrupted
from bluesky import plan_stubs as bps
from bluesky_stomp.messaging import MessageContext

from mx_bluesky.common.parameters.components import get_param_version
from mx_bluesky.common.parameters.constants import Status
from mx_bluesky.hyperion.parameters.components import UDCCleanup
from mx_bluesky.hyperion.plan_runner import PlanError
from mx_bluesky.hyperion.supervisor import SupervisorRunner

from ....unit_tests.hyperion.external_interaction.callbacks.test_alert_on_container_change import (
    TEST_VISIT,
)

BLUEAPI_SERVER_CONFIG = (
    "tests/system_tests/hyperion/supervisor/system_test_blueapi.yaml"
)


@pytest.fixture(scope="module")
def tpe():
    return ThreadPoolExecutor(max_workers=1)


@pytest.fixture(scope="module")
def mock_blueapi_server():
    with subprocess.Popen(
        [
            "blueapi",
            "--config",
            BLUEAPI_SERVER_CONFIG,
            "serve",
        ],
        env=environ | {"PYTHONPATH": getcwd() + "/tests"},
    ) as blueapi_server:
        try:
            yield blueapi_server
        finally:
            blueapi_server.terminate()


@pytest.fixture
def mock_bluesky_context(run_engine: RunEngine):
    loader = ConfigLoader(ApplicationConfig)
    loader.use_values_from_yaml(
        Path("tests/system_tests/hyperion/supervisor/supervisor_config.yaml")
    )
    supervisor_config = loader.load()
    yield BlueskyContext(configuration=supervisor_config, run_engine=run_engine)


@pytest.fixture
def client_config() -> ApplicationConfig:
    loader = ConfigLoader(ApplicationConfig)
    loader.use_values_from_yaml(
        Path("tests/system_tests/hyperion/supervisor/client_config.yaml")
    )
    return loader.load()


def get_event_bus_client(supervisor: SupervisorRunner) -> EventBusClient:
    return supervisor.blueapi_client._events  # type: ignore


@pytest.fixture
def supervisor_runner(supervisor_runner_no_ping: SupervisorRunner):
    supervisor_runner_no_ping.reset_callback_watchdog_timer()
    yield supervisor_runner_no_ping


@pytest.fixture
def supervisor_runner_no_ping(
    mock_bluesky_context: BlueskyContext, client_config: ApplicationConfig
):
    runner = SupervisorRunner(mock_bluesky_context, client_config, True)
    timeout = time.monotonic() + 30
    while time.monotonic() < timeout:
        if runner.is_connected():
            return runner
        sleep(1)
    else:
        raise AssertionError("Failed to connect to blueapi")


def handle_event(plan_started: Event, event_payload: AnyEvent, context: MessageContext):
    match event_payload:
        case DataEvent() as data_event:
            if (
                data_event.name == "start"
                and data_event.doc["plan_name"] == "clean_up_udc"
            ):
                plan_started.set()


@pytest.mark.system_test
def test_supervisor_connects_to_blueapi_and_stomp(
    mock_blueapi_server,
    mock_bluesky_context: BlueskyContext,
    client_config: ApplicationConfig,
    supervisor_runner: SupervisorRunner,
):
    params = UDCCleanup.model_validate({"parameter_model_version": get_param_version()})
    ebc = get_event_bus_client(supervisor_runner)

    received_message_event = Event()

    ebc.subscribe_to_all_events(partial(handle_event, received_message_event))
    assert supervisor_runner.current_status == Status.IDLE
    supervisor_runner.run_engine(
        supervisor_runner.decode_and_execute(TEST_VISIT, [params])
    )
    received_message_event.wait()


@pytest.mark.skip(reason="https://github.com/DiamondLightSource/blueapi/issues/1312")
def test_supervisor_continues_to_next_instruction_on_warning_error(
    supervisor_runner: SupervisorRunner,
):
    params = UDCCleanup.model_validate({"parameter_model_version": get_param_version()})
    supervisor_runner.run_engine(
        supervisor_runner.decode_and_execute("raise_warning_error", [params])
    )
    assert supervisor_runner.current_status == Status.FAILED


def test_supervisor_raises_request_abort_when_shutdown_requested(
    supervisor_runner: SupervisorRunner, tpe: ThreadPoolExecutor
):
    params = UDCCleanup.model_validate({"parameter_model_version": get_param_version()})
    ebc = get_event_bus_client(supervisor_runner)
    plan_aborted = Event()
    plan_called = Event()

    def handle_abort(event_payload: AnyEvent, context: MessageContext):
        match event_payload:
            case WorkerEvent() as worker_event:
                if (
                    worker_event.state == WorkerState.IDLE
                    and worker_event.task_status
                    and worker_event.task_status.task_complete
                    and worker_event.task_status.task_failed
                ):
                    plan_aborted.set()

    ebc.subscribe_to_all_events(partial(handle_event, plan_called))
    ebc.subscribe_to_all_events(handle_abort)

    def shutdown_in_background():
        plan_called.wait(10)
        assert supervisor_runner.current_status == Status.BUSY
        assert supervisor_runner.blueapi_client.get_state() == WorkerState.RUNNING
        supervisor_runner.shutdown()
        assert supervisor_runner.current_status == Status.ABORTING

    fut = tpe.submit(shutdown_in_background)

    with pytest.raises(RunEngineInterrupted):
        supervisor_runner.run_engine(
            supervisor_runner.decode_and_execute("wait_for_abort", [params])
        )

    assert supervisor_runner.blueapi_client.get_state() == WorkerState.IDLE
    assert plan_aborted.wait(10)
    fut.result()


def test_supervisor_raises_plan_error_when_plan_fails_with_other_exception(
    supervisor_runner: SupervisorRunner,
):
    params = UDCCleanup.model_validate({"parameter_model_version": get_param_version()})
    with pytest.raises(PlanError, match="Exception raised during plan execution:"):
        supervisor_runner.run_engine(
            supervisor_runner.decode_and_execute("raise_other_error", [params])
        )
    assert supervisor_runner.current_status == Status.FAILED


def test_shutdown_raises_run_engine_interrupted_when_idle(
    supervisor_runner: SupervisorRunner, tpe: ThreadPoolExecutor
):
    plan_started = Event()

    def idle_plan():
        plan_started.set()
        while True:
            yield from bps.sleep(1)

    def shutdown_in_background():
        plan_started.wait(10)
        supervisor_runner.shutdown()

    fut = tpe.submit(shutdown_in_background)

    with pytest.raises(RunEngineInterrupted):
        supervisor_runner.run_engine(idle_plan())

    fut.result()


async def test_supervisor_checks_for_external_callback_ping(
    supervisor_runner_no_ping: SupervisorRunner, tpe: ThreadPoolExecutor
):
    ebc = get_event_bus_client(supervisor_runner_no_ping)
    received_message_event = Event()
    ebc.subscribe_to_all_events(partial(handle_event, received_message_event))
    params = UDCCleanup.model_validate({"parameter_model_version": get_param_version()})

    def run_test_in_background():
        sleep(1)
        assert not received_message_event.is_set()
        supervisor_runner_no_ping.reset_callback_watchdog_timer()
        received_message_event.wait(1)

    fut = tpe.submit(run_test_in_background)
    supervisor_runner_no_ping.run_engine(
        supervisor_runner_no_ping.decode_and_execute(TEST_VISIT, [params])
    )
    fut.result()


def test_supervisor_raises_plan_error_when_external_callbacks_watchdog_expired(
    supervisor_runner_no_ping: SupervisorRunner,
):
    runner = supervisor_runner_no_ping
    runner.EXTERNAL_CALLBACK_WATCHDOG_TIMER_S = 0.5  # type: ignore
    runner.reset_callback_watchdog_timer()
    params = UDCCleanup.model_validate({"parameter_model_version": get_param_version()})
    # Allow callback watchdog to expire
    sleep(1)
    with pytest.raises(PlanError, match="External callback watchdog timer expired.*"):
        runner.run_engine(runner.decode_and_execute(TEST_VISIT, [params]))
