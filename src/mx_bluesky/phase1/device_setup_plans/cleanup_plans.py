from __future__ import annotations

from typing import Protocol, runtime_checkable

import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.devices.eiger import EigerDetector
from dodal.devices.zebra.zebra import Zebra
from dodal.devices.zebra.zebra_controlled_shutter import (
    ZebraShutter,
)
from dodal.devices.zocalo import ZocaloResults

from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.phase1.device_setup_plans.setup_zebra import (
    tidy_up_zebra_after_gridscan,
)


@runtime_checkable
class GridscanTidyDevices(Protocol):
    zocalo: ZocaloResults
    zebra: Zebra
    sample_shutter: ZebraShutter
    eiger: EigerDetector


def gridscan_generic_tidy(
    xrc_composite: GridscanTidyDevices, group, wait=True
) -> MsgGenerator:
    LOGGER.info("Tidying up Zebra")
    yield from tidy_up_zebra_after_gridscan(
        xrc_composite.zebra, xrc_composite.sample_shutter, group=group, wait=wait
    )
    LOGGER.info("Tidying up Zocalo")
    # make sure we don't consume any other results
    yield from bps.unstage(xrc_composite.zocalo, group=group, wait=wait)

    # Turn off dev/shm streaming to avoid filling disk, see https://github.com/DiamondLightSource/hyperion/issues/1395
    LOGGER.info("Turning off Eiger dev/shm streaming")
    yield from bps.abs_set(xrc_composite.eiger.odin.fan.dev_shm_enable, 0)  # type: ignore # Fix types in ophyd-async (https://github.com/DiamondLightSource/mx-bluesky/issues/855)
