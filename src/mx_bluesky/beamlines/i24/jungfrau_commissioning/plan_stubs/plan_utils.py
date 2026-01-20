from collections.abc import Callable
from typing import cast

import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.common.watcher_utils import log_on_percentage_complete
from dodal.devices.i24.commissioning_jungfrau import CommissioningJungfrau
from ophyd_async.core import (
    TriggerInfo,
    WatchableAsyncStatus,
)
from ophyd_async.fastcs.jungfrau import GainMode

from mx_bluesky.common.utils.log import LOGGER

JF_COMPLETE_GROUP = "JF complete"


def fly_jungfrau(
    jungfrau: CommissioningJungfrau,
    trigger_info: TriggerInfo,
    gain_mode: GainMode,
    wait: bool = False,
    log_on_percentage_prefix="Jungfrau data collection triggers received",
    read_hardware_after_prepare_plan: Callable[..., MsgGenerator]
    | None = None,  # Param needs refactor: https://github.com/DiamondLightSource/mx-bluesky/issues/819
) -> MsgGenerator[WatchableAsyncStatus]:
    """Stage, prepare, and kickoff Jungfrau with a configured TriggerInfo. Optionally wait
    for completion.

    Any plan using this stub MUST stage the Jungfrau with the stage_decorator and open a run,
    ideally using the run_decorator.

    Args:
    jungfrau: Jungfrau device.
    trigger_info: TriggerInfo which should be acquired using jungfrau util functions.
    gain_mode: Which gain mode to put the Jungfrau into before starting the acquisition.
    wait: Optionally block until data collection is complete.
    log_on_percentage_prefix: String that will be appended to the "percentage completion" logging message.
    read_hardware_after_prepare_plan: Optionally add a plan which will be ran in between preparing the jungfrau and starting
    acquisition. This is useful for reading devices after they have been prepared, especially since the file writing path
    is calculated during prepare.
    """

    LOGGER.info(f"Setting Jungfrau to gain mode {gain_mode}")
    yield from bps.mv(jungfrau.drv.gain_mode, gain_mode)
    LOGGER.info("Preparing detector...")
    yield from bps.prepare(jungfrau, trigger_info, wait=True)
    LOGGER.info("Detector prepared")
    if read_hardware_after_prepare_plan:
        yield from read_hardware_after_prepare_plan()
    yield from bps.kickoff(jungfrau, wait=True)
    LOGGER.info("Waiting for acquisition to complete...")
    status = yield from bps.complete(jungfrau, group=JF_COMPLETE_GROUP)

    # StandardDetector.complete converts regular status to watchable status,
    # but bluesky plan stubs can't see this currently
    status = cast(WatchableAsyncStatus, status)
    log_on_percentage_complete(status, log_on_percentage_prefix, 10)
    if wait:
        yield from bps.wait(JF_COMPLETE_GROUP)
    return status
