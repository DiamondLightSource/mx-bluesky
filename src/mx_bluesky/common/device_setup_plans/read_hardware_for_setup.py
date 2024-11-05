import bluesky.plan_stubs as bps
from dodal.devices.eiger import EigerDetector

from mx_bluesky.common.parameters.constants import DocDescriptorNames


def read_hardware_for_zocalo(detector: EigerDetector):
    """ "
    If the RunEngine is subscribed to the ZocaloCallback, this plan will also trigger zocalo.
    A bluesky run must be open to use this plan
    """
    yield from bps.create(name=DocDescriptorNames.ZOCALO_HW_READ)
    yield from bps.read(detector.odin.file_writer.id)  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
    yield from bps.save()
