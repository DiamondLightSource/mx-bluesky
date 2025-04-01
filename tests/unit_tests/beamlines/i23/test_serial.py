import pytest
from bluesky.simulators import RunEngineSimulator
from dodal.devices.motors import SixAxisGonio
from ophyd_async.core import init_devices

from mx_bluesky.beamlines.i23.serial import serial_collection


@pytest.fixture
def mock_gonio():
    with init_devices(mock=True):
        gonio = SixAxisGonio("", name="gonio")
    return gonio


def test_when_grid_scan_called_then_expected_x_y_set(
    sim_run_engine: RunEngineSimulator, mock_gonio: SixAxisGonio
):
    msgs = sim_run_engine.simulate_plan(
        serial_collection(4, 4, 0.1, 0.1, 30, mock_gonio)
    )
    x_moves = [
        msg for msg in msgs if msg.command == "set" and msg.obj.name == "gonio-x"
    ]
    y_moves = [
        msg for msg in msgs if msg.command == "set" and msg.obj.name == "gonio-y"
    ]
    assert len(x_moves) == 4 * 4 + 1  # Additional 1 for the initial move
    assert len(y_moves) == 4 * 4 + 1
