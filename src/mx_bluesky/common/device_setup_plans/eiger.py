from __future__ import annotations

from bluesky import plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.devices.eiger import EigerDetector

from mx_bluesky.common.parameters.device_composites import (
    FlyScanEssentialDevices,
    TGonioWithOmega,
)
from mx_bluesky.common.utils.log import LOGGER


def tidy_eiger(
    composite: FlyScanEssentialDevices[TGonioWithOmega, EigerDetector],
) -> MsgGenerator:
    """Turn off Eiger dev/shm. Ran after the beamline-specific tidy plan"""

    # Turn off dev/shm streaming to avoid filling disk, see https://github.com/DiamondLightSource/hyperion/issues/1395
    LOGGER.info("Turning off Eiger dev/shm streaming")
    # Fix types in ophyd-async (https://github.com/DiamondLightSource/mx-bluesky/issues/855)
    yield from bps.abs_set(
        composite.detector.odin.fan.dev_shm_enable,  # type: ignore # until https://github.com/DiamondLightSource/mx-bluesky/issues/1076
        0,
        wait=True,
    )
