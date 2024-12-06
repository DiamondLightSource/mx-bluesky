import numpy as np
from bluesky import plan_stubs as bps
from dodal.devices.smargon import Smargon

from mx_bluesky.hyperion.exceptions import SampleException


def move_smargon_warn_on_out_of_range(
    smargon: Smargon, position: np.ndarray | list[float] | tuple[float, float, float]
):
    """Throws a SampleException if the specified position is out of range for the
    smargon. Otherwise moves to that position."""
    limits = yield from smargon.get_xyz_limits()
    if not limits.position_valid(position):
        raise SampleException(
            "Pin tip centring failed - pin too long/short/bent and out of range"
        )
    yield from bps.mv(
        smargon.x,  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
        position[0],  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
        smargon.y,  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
        position[1],  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
        smargon.z,  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
        position[2],  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
    )
