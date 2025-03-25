import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.devices.aithre_lasershaping.laser_robot import LaserRobot, SampleLocation


def robot_exercise(robot: LaserRobot, sample_location: SampleLocation) -> MsgGenerator:
    yield from bps.abs_set(robot, sample_location, wait=True)
