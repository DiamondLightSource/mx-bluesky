import numpy as np
from bluesky import plan_stubs as bps
from bluesky.utils import FailedStatus
from dodal.devices.motors import XYZOmegaStage
from ophyd_async.epics.motor import MotorLimitsException

from mx_bluesky.common.utils.exceptions import SampleException


def move_gonio_warn_on_out_of_range(
    gonio: XYZOmegaStage,
    position: np.ndarray | list[float] | tuple[float, float, float],
):
    """
    Throws a SampleException if the specified position is out of range for the
    gonio. Otherwise moves to that position. The check is from ophyd-async
    """
    group = "move_warn_out_of_range"
    try:
        yield from bps.abs_set(gonio.x, position[0], group=group, wait=True)
        yield from bps.abs_set(gonio.y, position[1], group=group, wait=True)
        yield from bps.abs_set(gonio.z, position[2], group=group, wait=True)
        yield from bps.wait(group=group)
    except FailedStatus as fs:
        if isinstance(fs.__cause__, MotorLimitsException):
            raise SampleException(
                "Pin tip centring failed - pin too long/short/bent and out of range"
            ) from fs.__cause__
        else:
            raise fs
