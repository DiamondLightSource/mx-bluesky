import numpy as np
from bluesky import plan_stubs as bps
from dodal.devices.smargon import CombinedMove, Smargon


def move_smargon_warn_on_out_of_range(
    smargon: Smargon, position: np.ndarray | list[float] | tuple[float, float, float]
):
    """Moves Smargon to the specific position. Motor limits are handled by ophyd_async"""
    yield from bps.mv(
        smargon, CombinedMove(x=position[0], y=position[1], z=position[2])
    )
