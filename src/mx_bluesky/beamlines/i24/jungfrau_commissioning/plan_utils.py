from typing import cast

import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.common.watcher_utils import log_on_percentage_complete
from ophyd_async.core import (
    TriggerInfo,
    WatchableAsyncStatus,
)
from ophyd_async.fastcs.jungfrau import (
    Jungfrau,
)

from mx_bluesky.common.utils.log import LOGGER


def fly_jungfrau(
    jungfrau: Jungfrau, trigger_info: TriggerInfo, wait: bool = False
) -> MsgGenerator[WatchableAsyncStatus]:
    """Stage, prepare, and kickoff Jungfrau with a configured TriggerInfo. Optionally wait
    for completion.

    Note that this plan doesn't include unstaging of the Jungfrau.

    Args:
    jungfrau: Jungfrau device.
    trigger_info: TriggerInfo which should be acquired using jungfrau util functions create_jungfrau_internal_triggering_info
        or create_jungfrau_external_triggering_info.
    wait: Optionally block until data collection is complete.
    """

    yield from bps.stage(jungfrau)
    LOGGER.info("Setting up detector...")
    yield from bps.prepare(jungfrau, trigger_info, wait=True)
    LOGGER.info("Detector prepared. Starting acquisition")
    yield from bps.kickoff(jungfrau, wait=True)
    LOGGER.info("Waiting for acquisition to complete...")
    status = yield from bps.complete(jungfrau, group="jf_complete")

    # StandardDetector.complete converts regular status to watchable status,
    # but bluesky plan stubs can't see this currently
    status = cast(WatchableAsyncStatus, status)
    log_on_percentage_complete(status, "Jungfrau data collection triggers recieved", 10)
    if wait:
        yield from bps.wait("jf_complete")
    return status
