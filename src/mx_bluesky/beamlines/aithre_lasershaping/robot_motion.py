import bluesky.plan_stubs as bps
from bluesky.run_engine import RunEngine
from bluesky.utils import MsgGenerator
from dodal.beamlines.aithre import robot
from dodal.devices.aithre_lasershaping.laser_robot import LaserRobot, SampleLocation


def robot_load(robot: LaserRobot, sample_location: SampleLocation) -> MsgGenerator:
    yield from bps.abs_set(robot, sample_location, wait=True)


RE = RunEngine()
sample_loc = SampleLocation(1, 1)
rob = robot(connect_immediately=True)

RE(robot_load(rob, sample_loc))
