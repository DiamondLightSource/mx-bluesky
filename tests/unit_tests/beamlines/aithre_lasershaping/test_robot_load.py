import pytest
from bluesky.run_engine import RunEngine
from dodal.beamlines import aithre
from dodal.devices.aithre_lasershaping.laser_robot import LaserRobot

# from mx_bluesky.beamlines.aithre_lasershaping import robot_exercise


@pytest.fixture
def robot(RE: RunEngine) -> LaserRobot:
    return aithre.robot()


# def test_robot_load(RE: RunEngine, robot: LaserRobot):
#     msgs = RE(robot_exercise(robot, sample_location))
