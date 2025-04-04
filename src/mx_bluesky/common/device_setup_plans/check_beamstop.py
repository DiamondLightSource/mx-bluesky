import bluesky.plan_stubs as bps
from dodal.devices.mx_phase1.beamstop import Beamstop, BeamstopPositions

from mx_bluesky.common.utils.log import LOGGER


class BeamstopException(Exception):
    pass


def check_beamstop(beamstop: Beamstop):
    """
    Check the current position of the beamstop to ensure it is in position for data collection
    Args:
        beamstop: The beamstop device

    Raises:
        BeamstopException: If the beamstop is in any other position than DATA_COLLECTION
    """
    current_pos = yield from bps.rd(beamstop.selected_pos)
    if current_pos != BeamstopPositions.DATA_COLLECTION:
        LOGGER.info(f"Beamstop check failed: position {current_pos}")
        raise BeamstopException(
            f"Beamstop is not DATA_COLLECTION, current state is {current_pos}"
        )

    LOGGER.info("Beamstop check ok")
