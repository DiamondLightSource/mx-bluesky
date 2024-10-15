import bluesky.plan_stubs as bps
from dodal.devices.eiger import EigerDetector

from mx_bluesky.parameters.constants import MxConstants


def read_hardware_for_zocalo(detector: EigerDetector):
    # Bluesky run must be open to use this plan
    yield from bps.create(name=MxConstants.DESCRIPTORS.ZOCALO_HW_READ)
    yield from bps.read(detector.odin.file_writer.id)  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
    yield from bps.save()
