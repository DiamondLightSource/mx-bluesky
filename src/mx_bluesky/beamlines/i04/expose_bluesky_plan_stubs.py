from typing import Any

import bluesky.plan_stubs as bps
from dodal.common import inject

from mx_bluesky.common.utils.log import LOGGER


def move_device(device: str, value: Any):
    device = inject(device)
    yield from bps.mv(device, value)
    LOGGER.info("Done!")


def read_device(device: str):
    device = inject(device)
    value = yield from bps.rd(device)
    LOGGER.info(f"Read {device}, got {value}.")
