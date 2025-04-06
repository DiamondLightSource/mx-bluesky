from unittest.mock import MagicMock, patch

import pytest
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from dodal.devices.motors import SixAxisGonio
from ophyd_async.core import init_devices

from mx_bluesky.beamlines.i23.serial import one_nd_step, serial_collection


@pytest.fixture
def mock_gonio():
    with init_devices(mock=True):
        gonio = SixAxisGonio("", name="gonio")
    return gonio


def test_when_grid_scan_called_then_expected_x_y_set(
    sim_run_engine: RunEngineSimulator, mock_gonio: SixAxisGonio
):
    msgs = sim_run_engine.simulate_plan(
        serial_collection(4, 4, 0.1, 0.1, 30, 1.0, mock_gonio)
    )
    x_moves = [
        msg for msg in msgs if msg.command == "set" and msg.obj.name == "gonio-x"
    ]
    y_moves = [
        msg for msg in msgs if msg.command == "set" and msg.obj.name == "gonio-y"
    ]
    assert len(x_moves) == 4 * 4 + 1  # Additional 1 for the initial move
    assert len(y_moves) == 4 * 4 + 1

    assert x_moves[1].args[0] == pytest.approx(0.1)
    assert y_moves[5].args[0] == pytest.approx(0.1)


def test_omega_moves_twice_for_every_point(
    sim_run_engine: RunEngineSimulator, mock_gonio: SixAxisGonio
):
    msgs = sim_run_engine.simulate_plan(
        serial_collection(4, 4, 0.1, 0.1, 30, 1.0, mock_gonio)
    )
    omega_moves = [
        msg for msg in msgs if msg.command == "set" and msg.obj.name == "gonio-omega"
    ]
    assert len(omega_moves) == (4 * 4) * 2


@patch("mx_bluesky.beamlines.i23.serial.short_uid")
def test_when_stopped_at_point_then_omega_rotated_at_expected_speed(
    mock_short_uid: MagicMock,
    sim_run_engine: RunEngineSimulator,
    mock_gonio: SixAxisGonio,
):
    mock_short_uid.return_value = "test"
    msgs = sim_run_engine.simulate_plan(
        one_nd_step(
            [],
            {mock_gonio.x: 0.1, mock_gonio.y: 0.1},
            MagicMock(),
            mock_gonio.omega,
            30.0,
            1.0,
        )
    )
    msgs = assert_message_and_return_remaining(
        msgs, lambda msg: msg.command == "wait" and msg.kwargs["group"] == "test"
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "gonio-omega-velocity"
        and msg.args[0] == 1.0,
    )
    msgs = assert_message_and_return_remaining(msgs, lambda msg: msg.command == "wait")
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "gonio-omega"
        and msg.args[0] == 30.0,
    )


@patch("mx_bluesky.beamlines.i23.serial.short_uid")
def test_omega_set_to_0_at_max_velo_during_grid_move(
    mock_short_uid: MagicMock,
    sim_run_engine: RunEngineSimulator,
    mock_gonio: SixAxisGonio,
):
    mock_short_uid.return_value = "test"
    sim_run_engine.add_read_handler_for(mock_gonio.omega.max_velocity, 90)
    msgs = sim_run_engine.simulate_plan(
        one_nd_step(
            [],
            {mock_gonio.x: 0.1, mock_gonio.y: 0.1},
            MagicMock(),
            mock_gonio.omega,
            30.0,
            1.0,
        )
    )
    msgs = assert_message_and_return_remaining(
        msgs, lambda msg: msg.command == "set" and msg.obj.name == "gonio-x"
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "gonio-omega-velocity"
        and msg.args[0] == 90,
    )
    msgs = assert_message_and_return_remaining(msgs, lambda msg: msg.command == "wait")
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "gonio-omega"
        and msg.args[0] == 0,
    )
    msgs = assert_message_and_return_remaining(
        msgs, lambda msg: msg.command == "wait" and msg.kwargs["group"] == "test"
    )
