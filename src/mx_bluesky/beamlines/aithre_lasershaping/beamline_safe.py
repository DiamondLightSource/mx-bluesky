import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.common import inject
from dodal.devices.aithre_lasershaping.goniometer import Goniometer
from dodal.devices.aithre_lasershaping.laser_robot import ForceBit, LaserRobot


def check_beamline_safe(
    robot: LaserRobot = inject("robot"), goniometer: Goniometer = inject("goniometer")
) -> MsgGenerator:
    pvs = [
        goniometer.x,
        goniometer.y,
        goniometer.z,
        goniometer.sampy,
        goniometer.sampz,
        goniometer.omega,
    ]

    values: list[float] = []
    for pv in pvs:
        values.append((yield from bps.rd(pv)))

    set_value = (
        ForceBit.ON.value
        if all(round(value, 3) == 0 for value in values)
        else ForceBit.NO.value
    )
    yield from bps.abs_set(robot.set_beamline_safe, set_value, wait=True)
