from collections.abc import Iterator
from os import environ
from unittest.mock import patch

import pytest

# Ensure that the blueapi entry point is not invoked by doctest as this will fail
collect_ignore = ["src/mx_bluesky/hyperion/blueapi/plans.py"]

environ["HYPERION_TEST_MODE"] = "true"


pytest_plugins = [
    "dodal.testing.fixtures.run_engine",
    "dodal.testing.fixtures.config_server",
]


def pytest_addoption(parser):
    parser.addoption(
        "--logging",
        action="store_true",
        default=False,
        help="Log during all tests (not just those that are testing logging logic)",
    )


@pytest.fixture(scope="session", autouse=True)
def default_session_fixture() -> Iterator[None]:
    print("Patching bluesky 0MQ Publisher in __main__ for the whole session")
    with patch("mx_bluesky.hyperion.plan_runner.Publisher"):
        yield
