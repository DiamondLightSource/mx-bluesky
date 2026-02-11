import math

import pytest
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from dodal.devices.aithre_lasershaping.goniometer import Goniometer
from ophyd_async.core import set_mock_value
from ophyd_async.epics.motor import Motor

from mx_bluesky.beamlines.aithre_lasershaping import (
    change_goniometer_turn_speed,
    go_to_furthest_maximum,
    jog_sample,
    rotate_goniometer_relative,
)
from mx_bluesky.beamlines.aithre_lasershaping.goniometer_controls import JogDirection


def test_goniometer_relative_rotation(
    sim_run_engine: RunEngineSimulator, aithre_gonio: Goniometer
):
    msgs = sim_run_engine.simulate_plan(rotate_goniometer_relative(15, aithre_gonio))
    assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "goniometer-omega"
        and msg.args[0] == 15,
    )


def test_change_goniometer_turn_speed(
    sim_run_engine: RunEngineSimulator, aithre_gonio: Goniometer
):
    msgs = sim_run_engine.simulate_plan(change_goniometer_turn_speed(40, aithre_gonio))
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
    aithre_gonio: Goniometer,
    initial_position: float,
    expected_set_value: float,
    run_engine: RunEngine,
):
    set_mock_value(aithre_gonio.omega.user_readback, initial_position)

    run_engine(go_to_furthest_maximum(aithre_gonio))

    assert await aithre_gonio.omega.user_setpoint.get_value() == expected_set_value


@pytest.mark.parametrize(
    "directions, axis",
    [
        ((JogDirection.RIGHT, JogDirection.LEFT), "x"),
        ((JogDirection.ZPLUS, JogDirection.ZMINUS), "z"),
    ],
)
async def test_jog_sample_x_z(
    run_engine: RunEngine, aithre_gonio: Goniometer, directions, axis
):
    goniometer_axis: Motor = getattr(aithre_gonio, axis)

    run_engine(jog_sample(directions[0], 0.05, aithre_gonio))
    assert await goniometer_axis.user_readback.get_value() == 0.05

    run_engine(jog_sample(directions[1], 0.05, aithre_gonio))
    assert await goniometer_axis.user_readback.get_value() == 0


async def test_jog_sample_up_down(run_engine: RunEngine, aithre_gonio: Goniometer):
    set_mock_value(aithre_gonio.omega.user_readback, 60)

    run_engine(jog_sample(JogDirection.UP, 1, aithre_gonio))
    assert await aithre_gonio.sampz.user_readback.get_value() == pytest.approx(0.5)
    assert await aithre_gonio.sampy.user_readback.get_value() == pytest.approx(
        math.sqrt(3) / 2
    )

    run_engine(jog_sample(JogDirection.UP, 1, aithre_gonio))
    assert await aithre_gonio.sampz.user_readback.get_value() == pytest.approx(1)
    assert await aithre_gonio.sampy.user_readback.get_value() == pytest.approx(
        math.sqrt(3)
    )

    run_engine(jog_sample(JogDirection.DOWN, 1, aithre_gonio))
    assert await aithre_gonio.sampz.user_readback.get_value() == pytest.approx(0.5)
    assert await aithre_gonio.sampy.user_readback.get_value() == pytest.approx(
        math.sqrt(3) / 2
    )
