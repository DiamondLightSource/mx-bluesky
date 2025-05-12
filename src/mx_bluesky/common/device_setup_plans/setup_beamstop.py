import bluesky.plan_stubs as bps
from dodal.devices.mx_phase1.beamstop import Beamstop, BeamstopPositions

from mx_bluesky.common.utils.log import LOGGER


def setup_beamstop_for_collection(beamstop: Beamstop):
    current_pos = yield from bps.rd(beamstop.selected_pos)
    LOGGER.info(f"Beamstop position: {current_pos}")
    if current_pos != BeamstopPositions.DATA_COLLECTION:
        LOGGER.info(f"Moving beamstop to {beamstop.in_beam_position_mm}")
        yield from bps.abs_set(beamstop.x_mm, beamstop.in_beam_position_mm["x"])
        yield from bps.abs_set(beamstop.y_mm, beamstop.in_beam_position_mm["y"])
        yield from bps.abs_set(beamstop.z_mm, beamstop.in_beam_position_mm["z"])
