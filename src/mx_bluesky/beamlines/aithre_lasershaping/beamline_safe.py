import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.common import inject
from dodal.devices.aithre_lasershaping.goniometer import Goniometer
from dodal.devices.aithre_lasershaping.laser_robot import ForceBit, LaserRobot


def set_beamline_safe_on_robot(
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
        goniometer.stage_y,
        goniometer.stage_z,
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


def go_to_zero(
    goniometer: Goniometer = inject("goniometer"), group="move_to_zero", wait=True
) -> MsgGenerator:
    """
    Rotate the goniometer and set stages to zero in preparation for robot load/unload.
    Pass wait=False to avoid waiting for the move to complete.
    """
    yield from bps.abs_set(goniometer.omega, 0, group=group)
    yield from bps.abs_set(goniometer.x, 0, group=group)
    yield from bps.abs_set(goniometer.y, 0, group=group)
    yield from bps.abs_set(goniometer.z, 0, group=group)
    yield from bps.abs_set(goniometer.stage_y, 0, group=group)
    yield from bps.abs_set(goniometer.stage_z, 0, group=group)
    if wait:
        yield from bps.wait(group=group)
