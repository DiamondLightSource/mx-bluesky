from typing import Any

import bluesky.plan_stubs as bps
from bluesky.protocols import Movable, Readable
from dodal.plan_stubs.wrapped import move as mv

from mx_bluesky.common.utils.log import LOGGER


def move(device_or_signal: Movable, location: Any):
    yield from mv({device_or_signal: location})
    LOGGER.info("Done!")


def read(device_or_signal: Readable):
    value = yield from bps.read(device_or_signal)
    LOGGER.info(value)
