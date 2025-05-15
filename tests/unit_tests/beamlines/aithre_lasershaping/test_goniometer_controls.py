import pytest
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from dodal.beamlines import aithre
from dodal.devices.aithre_lasershaping.goniometer import AithreGoniometer
from dodal.devices.util.test_utils import patch_motor
from ophyd_async.core import init_devices

from mx_bluesky.beamlines.aithre_lasershaping import (
    change_goniometer_turn_speed,
    rotate_goniometer_relative,
)


@pytest.fixture
def goniometer(RE: RunEngine) -> AithreGoniometer:
    with init_devices(mock=True):
        gonio = aithre.goniometer(connect_immediately=True, mock=True)
    patch_motor(gonio.omega)
    patch_motor(gonio.y)
    patch_motor(gonio.z)
    return gonio


def test_goniometer_relative_rotation(
    sim_run_engine: RunEngineSimulator, goniometer: AithreGoniometer
):
    msgs = sim_run_engine.simulate_plan(rotate_goniometer_relative(15, goniometer))
    assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "goniometer-omega"
        and msg.args[0] == 15,
    )


def test_change_goniometer_turn_speed(
    sim_run_engine: RunEngineSimulator, goniometer: AithreGoniometer
):
    msgs = sim_run_engine.simulate_plan(change_goniometer_turn_speed(40, goniometer))
    assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "goniometer-omega-velocity"
        and msg.args[0] == 40,
    )


async def test_set_goniometer_j(goniometer: AithreGoniometer):
    await goniometer.omega.set(0)
    await goniometer.j.set(5)

    assert await goniometer.z.user_readback.get_value() == 5
    assert await goniometer.z.user_readback.get_value() == 0
