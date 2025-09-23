import numpy as np
from bluesky import plan_stubs as bps
from bluesky.utils import FailedStatus
from dodal.devices.motors import XYZOmegaStage
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
        if isinstance(fs.__cause__, MotorLimitsException):
            raise SampleException(
                "Pin tip centring failed - pin too long/short/bent and out of range"
            ) from fs.__cause__
        else:
            raise fs


def move_xyzomegastage_warn_on_out_of_range(
    xyzomegastage: XYZOmegaStage,
    position: np.ndarray | list[float] | tuple[float, float, float],
):
    """General version of move_smargon_warn_on_out_of_range"""
    try:
        yield from bps.mv(xyzomegastage.x, position[0])
    except FailedStatus as fs:
        if isinstance(fs.__cause__, MotorLimitsException):
            raise SampleException(
                "Pin tip centring failed - pin too long/short/bent and out of range"
            ) from fs.__cause__
        else:
            raise fs

    try:
        yield from bps.mv(xyzomegastage.y, position[1])
    except FailedStatus as fs:
        if isinstance(fs.__cause__, MotorLimitsException):
            raise SampleException(
                "Pin tip centring failed - pin too long/short/bent and out of range"
            ) from fs.__cause__
        else:
            raise fs

    try:
        yield from bps.mv(xyzomegastage.z, position[2])
    except FailedStatus as fs:
        if isinstance(fs.__cause__, MotorLimitsException):
            raise SampleException(
                "Pin tip centring failed - pin too long/short/bent and out of range"
            ) from fs.__cause__
        else:
            raise fs
