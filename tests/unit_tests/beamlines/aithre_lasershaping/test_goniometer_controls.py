import math

import pytest
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from dodal.beamlines import aithre
from dodal.devices.aithre_lasershaping.goniometer import Goniometer
from dodal.testing import patch_motor
from ophyd_async.core import init_devices
from ophyd_async.epics.motor import Motor
from ophyd_async.testing import set_mock_value

from mx_bluesky.beamlines.aithre_lasershaping import (
    change_goniometer_turn_speed,
    go_to_furthest_maximum,
    jog_sample,
    rotate_goniometer_relative,
)
from mx_bluesky.beamlines.aithre_lasershaping.goniometer_controls import JogDirection


@pytest.fixture
def goniometer(RE: RunEngine) -> Goniometer:
    with init_devices(mock=True):
        gonio = aithre.goniometer(connect_immediately=True, mock=True)

    patch_motor(gonio.omega)
    patch_motor(gonio.x)
    patch_motor(gonio.y)
    patch_motor(gonio.z)
    patch_motor(gonio.stage_y)
    patch_motor(gonio.stage_z)
    return gonio


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


@pytest.mark.parametrize(
    "initial_position, expected_set_value", [(-1, 3600), (0, 3600), (3600, -3600)]
)
async def test_go_to_furthest_maximum_real_run_engine(
    goniometer: Goniometer,
    initial_position: float,
    expected_set_value: float,
    RE: RunEngine,
):
    set_mock_value(goniometer.omega.user_readback, initial_position)

    RE(go_to_furthest_maximum(goniometer))

    assert await goniometer.omega.user_setpoint.get_value() == expected_set_value


@pytest.mark.parametrize(
    "directions, axis",
    [
        ((JogDirection.RIGHT, JogDirection.LEFT), "x"),
        ((JogDirection.ZPLUS, JogDirection.ZMINUS), "z"),
    ],
)
async def test_jog_sample_x_z(RE: RunEngine, goniometer: Goniometer, directions, axis):
    goniometer_axis: Motor = getattr(goniometer, axis)

    RE(jog_sample(directions[0], 0.05, goniometer))
    assert await goniometer_axis.user_readback.get_value() == 0.05

    RE(jog_sample(directions[1], 0.05, goniometer))
    assert await goniometer_axis.user_readback.get_value() == 0


async def test_jog_sample_up_down(RE: RunEngine, goniometer: Goniometer):
    set_mock_value(goniometer.omega.user_readback, 60)

    RE(jog_sample(JogDirection.UP, 1, goniometer))
    assert await goniometer.z.user_readback.get_value() == pytest.approx(0.5)
    assert await goniometer.y.user_readback.get_value() == pytest.approx(
        math.sqrt(3) / 2
    )

    RE(jog_sample(JogDirection.UP, 1, goniometer))
    assert await goniometer.z.user_readback.get_value() == pytest.approx(1)
    assert await goniometer.y.user_readback.get_value() == pytest.approx(math.sqrt(3))

    RE(jog_sample(JogDirection.DOWN, 1, goniometer))
    assert await goniometer.z.user_readback.get_value() == pytest.approx(0.5)
    assert await goniometer.y.user_readback.get_value() == pytest.approx(
        math.sqrt(3) / 2
    )
