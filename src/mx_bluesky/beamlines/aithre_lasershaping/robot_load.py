from dodal.common import inject
from dodal.devices.motors import XYZOmegaStage
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.robot import BartRobot, SampleLocation

from mx_bluesky.beamlines.aithre_lasershaping.robot_load_plan import (
    RobotLoadComposite,
    do_robot_load,
    robot_unload,
)


def aithre_robot_load(
    robot: BartRobot = inject("robot"),
    gonio: XYZOmegaStage = inject("gonio"),
    oav: OAV = inject("oav"),
    sample_loc: SampleLocation = inject("sample_loc"),
    sample_id: int = 0,
):
    composite = RobotLoadComposite(robot, gonio, oav, gonio)

    yield from do_robot_load(composite, sample_loc, sample_id)


def aithre_robot_unload(
    robot: BartRobot = inject("robot"),
    gonio: XYZOmegaStage = inject("gonio"),
    oav: OAV = inject("oav"),
):
    composite = RobotLoadComposite(robot, gonio, oav, gonio)
    yield from robot_unload(composite)
