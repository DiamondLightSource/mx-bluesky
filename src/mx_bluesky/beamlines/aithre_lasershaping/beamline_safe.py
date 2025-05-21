import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.common import inject
from dodal.devices.aithre_lasershaping.goniometer import Goniometer
from dodal.devices.aithre_lasershaping.laser_robot import ForceBit, LaserRobot


def set_beamline_safe(
    robot: LaserRobot = inject("robot"), goniometer: Goniometer = inject("goniometer")
) -> MsgGenerator:
    """
    The beamline safe PV is used in the Aithre laser shaping system to indicate whether
    the goniometer is in the correct position for the robot to load a sample. The robot
    is trained to load at the goniometer zero position, so if the translation and
    rotation axes of the goniometer are at zero, then the beamline safe PV bit is forced
    on.
    """
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
