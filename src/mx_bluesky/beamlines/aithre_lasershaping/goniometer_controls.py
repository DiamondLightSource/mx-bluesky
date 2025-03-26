import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.devices.aithre_lasershaping.goniometer import Goniometer


def rotate_goniometer_relative(goniometer: Goniometer, value: float) -> MsgGenerator:
    """Adjust the goniometer position incrementally"""
    yield from bps.rel_set(goniometer.omega, value, wait=True)
