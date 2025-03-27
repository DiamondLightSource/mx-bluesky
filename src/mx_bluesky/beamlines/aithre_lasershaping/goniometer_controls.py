import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.devices.aithre_lasershaping.goniometer import Goniometer


def change_goniometer_turn_speed(
    goniometer: Goniometer, velocity: float
) -> MsgGenerator:
    """Set the velocity of the goniometer"""
    yield from bps.mv(goniometer.omega.velocity, velocity)
