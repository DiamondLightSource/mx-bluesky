import datetime

from bluesky.utils import MsgGenerator
from dodal.common import inject
from dodal.devices.motors import XYZOmegaStage
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.oav.pin_image_recognition import PinTipDetection
from dodal.devices.robot import BartRobot

from mx_bluesky.beamlines.aithre_lasershaping.experiment_plans.robot_load_plan import (
    RobotLoadComposite,
    robot_load_and_snapshots_plan,
    robot_unload_plan,
)
from mx_bluesky.beamlines.aithre_lasershaping.parameters.constants import CONST
from mx_bluesky.beamlines.aithre_lasershaping.parameters.robot_load_parameters import (
    AithreRobotLoad,
)


def robot_load_and_snapshot(
    robot: BartRobot = inject("robot"),
    gonio: XYZOmegaStage = inject("gonio"),
    oav: OAV = inject("oav"),
    ptd: PinTipDetection = inject("ptd"),
    tip_offset_microns: float = 0,
    oav_config_file: str = CONST.OAV_CENTRING_FILE,
    sample_puck: int = 0,
    sample_pin: int = 0,
    sample_id: int = 0,
    sample_name: str = "test",
    visit: str = "cm40645-5",
) -> MsgGenerator:
    time_now = datetime.datetime.now()
    year_now = str(time_now.year)
    snapshot_directory = f"/dls/i23/data/{year_now}/{visit}/{sample_name}/snapshots"
    composite = RobotLoadComposite(robot, gonio, oav, gonio)
    params = AithreRobotLoad(
        sample_id=sample_id,
        sample_puck=sample_puck,
        sample_pin=sample_pin,
        snapshot_directory=snapshot_directory,
        visit=visit,
        beamline="BL23I",
    )

    yield from robot_load_and_snapshots_plan(
        composite, params, ptd, tip_offset_microns, oav_config_file
    )


def robot_unload(
    robot: BartRobot = inject("robot"),
    gonio: XYZOmegaStage = inject("gonio"),
    oav: OAV = inject("oav"),
    sample_puck: int = 0,
    sample_pin: int = 0,
    sample_id: int = 0,
    sample_name: str = "test",
    visit: str = "cm40645-5",
) -> MsgGenerator:
    time_now = datetime.datetime.now()
    year_now = str(time_now.year)
    snapshot_directory = f"/dls/i23/data/{year_now}/{visit}/{sample_name}/snapshots"
    composite = RobotLoadComposite(robot, gonio, oav, gonio)
    params = AithreRobotLoad(
        sample_id=sample_id,
        sample_puck=sample_puck,
        sample_pin=sample_pin,
        snapshot_directory=snapshot_directory,
        visit=visit,
        beamline="BL23I",
    )
    yield from robot_unload_plan(composite, params)
