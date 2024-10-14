import bluesky.plan_stubs as bps
from dodal.devices.eiger import EigerDetector

from mx_bluesky.i03.parameters.constants import CONST


def read_hardware_for_zocalo(detector: EigerDetector):
    yield from bps.create(name=CONST.DESCRIPTORS.ZOCALO_HW_READ)
    yield from bps.read(detector.odin.file_writer.id)  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
    yield from bps.save()
