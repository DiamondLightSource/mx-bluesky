import pytest
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from dodal.beamlines import aithre
from dodal.devices.aithre_lasershaping.goniometer import Goniometer

from mx_bluesky.beamlines.aithre_lasershaping import check_omega_performance


@pytest.fixture
def goniometer(RE: RunEngine) -> Goniometer:
    return aithre.goniometer(connect_immediately=True, mock=True)


def test_goniometer_omega_performance_check(
    sim_run_engine: RunEngineSimulator, goniometer: Goniometer
):
    msgs = sim_run_engine.simulate_plan(check_omega_performance(goniometer))
    assert len(msgs) == 132
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "goniometer-omega-velocity"
        and msg.args[0] == 5,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "goniometer-omega"
        and msg.args[0] == 300,
    )
