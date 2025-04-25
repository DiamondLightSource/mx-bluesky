from collections.abc import Iterator
from os import environ
from unittest.mock import patch

import pytest

environ["HYPERION_TEST_MODE"] = "true"


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
    with patch("mx_bluesky.hyperion.__main__.Publisher"):
        yield
