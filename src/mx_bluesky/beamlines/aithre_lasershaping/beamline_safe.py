import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.devices.aithre_lasershaping.goniometer import Goniometer
from dodal.devices.aithre_lasershaping.laser_robot import BeamlineSafe, LaserRobot


def check_beamline_safe(robot: LaserRobot, goniometer: Goniometer) -> MsgGenerator:
    pvs = [
        goniometer.x,
        goniometer.y,
        goniometer.z,
        goniometer.sampy,
        goniometer.sampz,
        goniometer.omega,
    ]

    values: list[float] = []
    for i in range(len(pvs)):
        values[i] = yield from bps.rd(pvs[i])

    set_value = (
        BeamlineSafe.ON
        if all(round(value, 3) == 0 for value in values)
        else BeamlineSafe.NO
    )
    yield from bps.abs_set(robot.set_beamline_safe, set_value, wait=True)
