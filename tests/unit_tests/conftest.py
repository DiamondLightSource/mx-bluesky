import asyncio
import time
from collections.abc import Callable
from types import ModuleType
from unittest.mock import MagicMock

import pytest
from bluesky.run_engine import RunEngine
from dodal.common.beamlines import beamline_parameters
from dodal.devices.zocalo import ZocaloTrigger
from dodal.utils import AnyDeviceFactory, collect_factories


@pytest.fixture
async def RE():
    RE = RunEngine(call_returns_result=True)
    # make sure the event loop is thoroughly up and running before we try to create
    # any ophyd_async devices which might need it
    timeout = time.monotonic() + 1
    while not RE.loop.is_running():
        await asyncio.sleep(0)
        if time.monotonic() > timeout:
            raise TimeoutError("This really shouldn't happen but just in case...")
    yield RE


MOCK_DAQ_CONFIG_PATH = "tests/devices/unit_tests/test_daq_configuration"
mock_paths = [
    ("DAQ_CONFIGURATION_PATH", MOCK_DAQ_CONFIG_PATH),
    ("ZOOM_PARAMS_FILE", "tests/devices/unit_tests/test_jCameraManZoomLevels.xml"),
    ("DISPLAY_CONFIG", "tests/devices/unit_tests/test_display.configuration"),
    ("LOOK_UPTABLE_DIR", "tests/devices/i10/lookupTables/"),
]
mock_attributes_table = {
    "i03": mock_paths,
    "i10": mock_paths,
    "i04": mock_paths,
    "s04": mock_paths,
    "i24": mock_paths,
}


def assert_event(mock_call, expected):
    actual = mock_call.args[0]
    if "data" in actual:
        actual = actual["data"]
    for k, v in expected.items():
        assert actual[k] == v, f"Mismatch in key {k}, {actual} <=> {expected}"


def mock_beamline_module_filepaths(bl_name, bl_module):
    if mock_attributes := mock_attributes_table.get(bl_name):
        [bl_module.__setattr__(attr[0], attr[1]) for attr in mock_attributes]
        beamline_parameters.BEAMLINE_PARAMETER_PATHS[bl_name] = (
            "tests/test_data/i04_beamlineParameters"
        )


def device_factories_for_beamline(beamline_module: ModuleType) -> set[AnyDeviceFactory]:
    return {
        f
        for f in collect_factories(beamline_module, include_skipped=True).values()
        if hasattr(f, "cache_clear")
    }


def modified_interactor_mock(assign_run_end: Callable | None = None):
    mock = MagicMock(spec=ZocaloTrigger)
    if assign_run_end:
        mock.run_end = assign_run_end
    return mock
