import subprocess
import time
from os import environ, getcwd
from pathlib import Path
from threading import Event
from time import sleep

import pytest
from blueapi.client.event_bus import AnyEvent, EventBusClient
from blueapi.config import ApplicationConfig, ConfigLoader
from blueapi.core import BlueskyContext, DataEvent
from bluesky import RunEngine
from bluesky_stomp.messaging import MessageContext

from mx_bluesky.common.parameters.components import get_param_version
from mx_bluesky.hyperion.parameters.components import UDCCleanup
from mx_bluesky.hyperion.supervisor import SupervisorRunner
from unit_tests.hyperion.external_interaction.callbacks.test_alert_on_container_change import (
    TEST_VISIT,
)

BLUEAPI_SERVER_CONFIG = (
    "tests/system_tests/hyperion/supervisor/system_test_blueapi.yaml"
)


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
            blueapi_server.kill()


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
    return supervisor.blueapi_client._events


@pytest.mark.system_test
def test_supervisor_connects_to_blueapi(
    mock_blueapi_server,
    mock_bluesky_context: BlueskyContext,
    client_config: ApplicationConfig,
):
    runner = SupervisorRunner(mock_bluesky_context, client_config, True)
    timeout = time.monotonic() + 30
    while time.monotonic() < timeout:
        if runner.is_connected():
            break
        sleep(1)
    else:
        raise AssertionError("Failed to connect to blueapi")

    plans = runner.blueapi_client.get_plans()
    for p in plans:
        print(f"{p}\n")
    params = UDCCleanup.model_validate({"parameter_model_version": get_param_version()})
    ebc = get_event_bus_client(runner)

    received_message_event = Event()

    def handle_event(event: AnyEvent, context: MessageContext):
        if isinstance(event, DataEvent):
            data_event: DataEvent = event
            if (
                data_event.name == "start"
                and data_event.doc["plan_name"] == "clean_up_udc"
            ):
                received_message_event.set()

    ebc.subscribe_to_all_events(handle_event)

    runner.run_engine(runner.decode_and_execute(TEST_VISIT, [params]))
    received_message_event.wait()
