from importlib import resources
from pathlib import Path
from unittest.mock import patch

import pytest
from dodal.beamlines import i03
from dodal.utils import collect_factories

BANNED_PATHS = [Path("/dls"), Path("/dls_sw")]


@pytest.fixture(scope="session")
def i03_device_factories():
    return [
        f
        for f in collect_factories(i03, include_skipped=True).values()
        if hasattr(f, "cache_clear")
    ]


@pytest.fixture(scope="function", autouse=True)
def clear_device_factory_caches_after_every_test(i03_device_factories):
    yield None
    for f in i03_device_factories:
        f.cache_clear()  # type: ignore


@pytest.fixture(autouse=True)
def patch_open_to_prevent_dls_reads_in_tests():
    unpatched_open = open
    project_folder = resources.files(__package__)
    assert isinstance(project_folder, Path)
    project_folder = project_folder.parent.parent.parent

    def patched_open(*args, **kwargs):
        requested_path = Path(args[0])
        if requested_path.is_absolute():
            for p in BANNED_PATHS:
                assert not requested_path.is_relative_to(
                    p
                ) or requested_path.is_relative_to(project_folder), (
                    f"Attempt to open {requested_path} from inside a unit test"
                )
        return unpatched_open(*args, **kwargs)

    with patch("builtins.open", side_effect=patched_open):
        yield []
