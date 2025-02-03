from __future__ import annotations

from enum import StrEnum

import bluesky.plan_stubs as bps
from bluesky.protocols import Readable
from dodal.devices.eiger import EigerDetector

from mx_bluesky.common.parameters.constants import (
    DocDescriptorNames,
)
from mx_bluesky.common.utils.log import LOGGER


class ReadHardwareTime(StrEnum):
    DURING_COLLECTION = "during collection"
    PRE_COLLECTION = "pre collection"


def read_hardware_plan(
    signals: list[Readable],
    read_hardware_time: ReadHardwareTime,
):
    LOGGER.info(f"Reading status of beamline for callbacks, {read_hardware_time}")
    event_name = (
        DocDescriptorNames.HARDWARE_READ_DURING
        if read_hardware_time == ReadHardwareTime.DURING_COLLECTION
        else DocDescriptorNames.HARDWARE_READ_PRE
    )
    yield from bps.create(name=event_name)
    for signal in signals:
        yield from bps.read(signal)
    yield from bps.save()


def read_hardware_for_zocalo(detector: EigerDetector):
    """ "
    If the RunEngine is subscribed to the ZocaloCallback, this plan will also trigger zocalo.
    """
    yield from bps.create(name=DocDescriptorNames.ZOCALO_HW_READ)
    yield from bps.read(detector.odin.file_writer.id)  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
    yield from bps.save()
