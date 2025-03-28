import pytest
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from dodal.beamlines import aithre
from dodal.devices.aithre_lasershaping.goniometer import Goniometer

from mx_bluesky.beamlines.aithre_lasershaping import (
    change_goniometer_turn_speed,
    rotate_goniometer_relative,
)


@pytest.fixture
def goniometer(RE: RunEngine) -> Goniometer:
    return aithre.goniometer(connect_immediately=True, mock=True)


def test_goniometer_relative_rotation(
    sim_run_engine: RunEngineSimulator, goniometer: Goniometer
):
    msgs = sim_run_engine.simulate_plan(rotate_goniometer_relative(15, goniometer))
    assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "goniometer-omega"
        and msg.args[0] == 15,
    )


def test_change_goniometer_turn_speed(
    sim_run_engine: RunEngineSimulator, goniometer: Goniometer
):
    msgs = sim_run_engine.simulate_plan(change_goniometer_turn_speed(40, goniometer))
    assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "goniometer-omega-velocity"
        and msg.args[0] == 40,
    )
