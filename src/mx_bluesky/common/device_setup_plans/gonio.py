import numpy as np
from bluesky import plan_stubs as bps
from bluesky.utils import FailedStatus
from dodal.devices.motors import XYZOmegaStage
from ophyd_async.epics.motor import MotorLimitsError

from mx_bluesky.common.utils.exceptions import SampleError


def move_gonio_warn_on_out_of_range(
    gonio: XYZOmegaStage,
    position: np.ndarray | list[float] | tuple[float, float, float],
):
    """
    Throws a SampleException if the specified position is out of range for the
    gonio. Otherwise moves to that position. The check is from ophyd-async
    """
    try:
        yield from bps.mv(
            gonio.x, position[0], gonio.y, position[1], gonio.z, position[2]
        )
    except FailedStatus as fs:
        if isinstance(fs.__cause__, MotorLimitsError):
            raise SampleError(
                "Pin tip centring failed - pin too long/short/bent and out of range"
            ) from fs.__cause__
        else:
            raise fs
