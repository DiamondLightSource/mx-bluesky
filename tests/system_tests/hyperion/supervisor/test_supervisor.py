import subprocess
from pathlib import Path

import pytest
from blueapi.config import ApplicationConfig, ConfigLoader
from blueapi.core import BlueskyContext
from bluesky import RunEngine

from mx_bluesky.common.parameters.components import get_param_version
from mx_bluesky.hyperion.parameters.components import Wait
from mx_bluesky.hyperion.supervisor import SupervisorRunner
from unit_tests.hyperion.external_interaction.callbacks.test_alert_on_container_change import (
    TEST_VISIT,
)


@pytest.fixture(scope="module")
def mock_blueapi_server():
    with subprocess.Popen(
        [
            "blueapi",
            "--config",
            "tests/system_tests/hyperion/supervisor/system_test_blueapi.yaml",
            "serve",
        ]
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


@pytest.mark.system_test
def test_supervisor_connects_to_blueapi(
    mock_blueapi_server: subprocess.Popen,
    mock_bluesky_context: BlueskyContext,
    client_config: ApplicationConfig,
):
    runner = SupervisorRunner(mock_bluesky_context, client_config, True)
    params = Wait.model_validate(
        {"parameter_model_version": get_param_version(), "duration_s": 0.1}
    )
    runner.decode_and_execute(TEST_VISIT, [params])
