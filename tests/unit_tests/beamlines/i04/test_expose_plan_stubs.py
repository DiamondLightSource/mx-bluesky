from unittest.mock import AsyncMock

import pytest
from bluesky import FailedStatus
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from dodal.devices.scintillator import Scintillator
from ophyd_async.core import (
    get_mock_put,
)

from mx_bluesky.beamlines.i04.expose_plan_stubs import move, read


def test_do_move_in_on_scintillator(
    scintillator: Scintillator,
    run_engine: RunEngine,
):
    scintillator._check_aperture_parked = AsyncMock()
    run_engine(move(scintillator.selected_pos, "In"))
    get_mock_put(scintillator.selected_pos).assert_called_once_with("In", wait=True)


def test_do_move_out_on_scintillator(
    scintillator: Scintillator,
    run_engine: RunEngine,
):
    scintillator._check_aperture_parked = AsyncMock()
    run_engine(move(scintillator.selected_pos, "Out"))
    get_mock_put(scintillator.selected_pos).assert_called_once_with("Out", wait=True)


def test_do_move_with_invalid_location_causes_error(
    scintillator: Scintillator,
    run_engine: RunEngine,
):
    scintillator._check_aperture_parked = AsyncMock()
    with pytest.raises(FailedStatus):
        run_engine(move(scintillator.selected_pos, "invalid"))


def test_read_does_a_read(
    scintillator: Scintillator,
    sim_run_engine: RunEngineSimulator,
):
    scintillator._check_aperture_parked = AsyncMock()
    msgs = sim_run_engine.simulate_plan(read(scintillator))
    assert_message_and_return_remaining(
        msgs,
        (lambda msg: msg.command == "read" and msg.obj.name == "scintillator"),
    )
