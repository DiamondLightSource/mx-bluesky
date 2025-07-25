import pytest
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from dodal.beamlines import aithre
from dodal.devices.aithre_lasershaping.goniometer import Goniometer
from dodal.devices.aithre_lasershaping.laser_robot import LaserRobot

from mx_bluesky.beamlines.aithre_lasershaping import (
    go_to_zero,
    set_beamline_safe_on_robot,
)


@pytest.fixture
def goniometer(RE: RunEngine) -> Goniometer:
    return aithre.goniometer(connect_immediately=True, mock=True)


@pytest.fixture
def robot(RE: RunEngine) -> LaserRobot:
    return aithre.robot(connect_immediately=True, mock=True)


@pytest.mark.parametrize(
    "set_pv_name, set_value",
    [
        ["omega", -90],
        ["x", 0.5],
        ["y", -10],
        ["z", 2],
        ["sampy", 0.25],
        ["sampz", -0.76],
    ],
)
async def test_beamline_safe_reads_unsafe_correctly(
    sim_run_engine: RunEngineSimulator,
    robot: LaserRobot,
    goniometer: Goniometer,
    set_pv_name: str,
    set_value: float,
):
    # Should be replaced by read_handler when https://github.com/bluesky/bluesky/issues/1906 is fixed
    def locate_pv(_):
        return {"readback": set_value}

    sim_run_engine.add_handler("locate", locate_pv, "goniometer-" + set_pv_name)

    msgs = sim_run_engine.simulate_plan(set_beamline_safe_on_robot(robot, goniometer))
    assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "robot-set_beamline_safe"
        and msg.args[0] == "No",
    )


async def test_beamline_safe_reads_safe_correctly(
    sim_run_engine: RunEngineSimulator,
    robot: LaserRobot,
    goniometer: Goniometer,
):
    msgs = sim_run_engine.simulate_plan(set_beamline_safe_on_robot(robot, goniometer))

    assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "robot-set_beamline_safe"
        and msg.args[0] == "On",
    )


async def test_go_to_zero_gives_expected_result(
    sim_run_engine: RunEngineSimulator,
    goniometer: Goniometer,
):
    msgs = sim_run_engine.simulate_plan(go_to_zero(goniometer=goniometer, wait=False))

    assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "goniometer-omega"
        and msg.args[0] == 0,
    )
    assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "goniometer-x"
        and msg.args[0] == 0,
    )
    assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "goniometer-y"
        and msg.args[0] == 0,
    )
    assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "goniometer-z"
        and msg.args[0] == 0,
    )
    assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "goniometer-sampy"
        and msg.args[0] == 0,
    )
    assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "goniometer-sampz"
        and msg.args[0] == 0,
    )
