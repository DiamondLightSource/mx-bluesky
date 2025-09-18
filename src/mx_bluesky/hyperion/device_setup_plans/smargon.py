import numpy as np
from bluesky import plan_stubs as bps
from bluesky.utils import FailedStatus
from dodal.devices.smargon import CombinedMove, Smargon
from ophyd_async.epics.motor import MotorLimitsException

from mx_bluesky.common.utils.exceptions import SampleException


def move_smargon_warn_on_out_of_range(
    smargon: Smargon, position: np.ndarray | list[float] | tuple[float, float, float]
):
    """Throws a SampleException if the specified position is out of range for the
    smargon. Otherwise moves to that position. The check is from ophyd-async"""
    try:
        yield from bps.mv(
            smargon, CombinedMove(x=position[0], y=position[1], z=position[2])
        )
    except FailedStatus as fs:
        print(f"FailedStatus attributes: {dir(fs)}")
        print(f"FailedStatus args: {fs.args}")
        print(f"FailedStatus __cause__: {fs.__cause__}")
        if isinstance(fs.exception, MotorLimitsException):
            raise SampleException(
                "Pin tip centring failed - pin too long/short/bent and out of range"
            ) from fs.exception
        else:
            raise
