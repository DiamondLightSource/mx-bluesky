from dodal.common import inject
from dodal.devices.motors import XYZOmegaStage
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.robot import BartRobot, SampleLocation

from mx_bluesky.beamlines.aithre_lasershaping.parameters.robot_load_parameters import (
    AithreRobotLoad,
)
from mx_bluesky.beamlines.aithre_lasershaping.robot_load_plan import (
    RobotLoadComposite,
    robot_load_and_snapshots_plan,
    robot_unload_plan,
)


def robot_load_and_snapshot(
    robot: BartRobot = inject("robot"),
    gonio: XYZOmegaStage = inject("gonio"),
    oav: OAV = inject("oav"),
    sample_loc: SampleLocation = inject("sample_loc"),
    sample_id: int = 0,
    visit: str = "cm40645-1",
):
    composite = RobotLoadComposite(robot, gonio, oav, gonio)
    params = AithreRobotLoad(
        sample_id=sample_id,
        sample_puck=sample_loc.puck,
        sample_pin=sample_loc.pin,
        snapshot_directory="/dls/tmp/wck38436/snapshots",
        visit=visit,
        beamline="BL23I",
    )

    yield from robot_load_and_snapshots_plan(composite, params)


def robot_unload(
    robot: BartRobot = inject("robot"),
    gonio: XYZOmegaStage = inject("gonio"),
    oav: OAV = inject("oav"),
    sample_loc: SampleLocation = inject("sample_loc"),
    sample_id: int = 0,
    visit: str = "cm40645-1",
):
    composite = RobotLoadComposite(robot, gonio, oav, gonio)
    params = AithreRobotLoad(
        sample_id=sample_id,
        sample_puck=sample_loc.puck,
        sample_pin=sample_loc.pin,
        snapshot_directory="/dls/tmp/wck38436/snapshots",
        visit=visit,
        beamline="BL23I",
    )
    yield from robot_unload_plan(composite, params)
