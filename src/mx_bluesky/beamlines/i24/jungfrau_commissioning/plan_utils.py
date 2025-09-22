from typing import cast

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
from bluesky.utils import MsgGenerator
from dodal.common.watcher_utils import log_on_percentage_complete
from dodal.devices.i24.commissioning_jungfrau import CommissioningJungfrau
from ophyd_async.core import (
    StaticFilenameProvider,
    TriggerInfo,
    WatchableAsyncStatus,
)

from mx_bluesky.common.utils.log import LOGGER

JF_COMPLETE_GROUP = "JF complete"


def fly_jungfrau(
    jungfrau: CommissioningJungfrau, trigger_info: TriggerInfo, wait: bool = False
) -> MsgGenerator[WatchableAsyncStatus]:
    """Stage, prepare, and kickoff Jungfrau with a configured TriggerInfo. Optionally wait
    for completion.

    Note that this plan doesn't include unstaging of the Jungfrau, and a run must be open
    before this plan is called.

    Args:
    jungfrau: Jungfrau device.
    trigger_info: TriggerInfo which should be acquired using jungfrau util functions create_jungfrau_internal_triggering_info
        or create_jungfrau_external_triggering_info.
    wait: Optionally block until data collection is complete.
    """

    @bpp.contingency_decorator(except_plan=lambda _: (yield from bps.unstage(jungfrau)))
    def _fly_with_unstage_contingency():
        yield from bps.stage(jungfrau)
        LOGGER.info("Setting up detector...")
        yield from bps.prepare(jungfrau, trigger_info, wait=True)
        LOGGER.info("Detector prepared. Starting acquisition")
        yield from bps.kickoff(jungfrau, wait=True)
        LOGGER.info("Waiting for acquisition to complete...")
        status = yield from bps.complete(jungfrau, group=JF_COMPLETE_GROUP)

        # StandardDetector.complete converts regular status to watchable status,
        # but bluesky plan stubs can't see this currently
        status = cast(WatchableAsyncStatus, status)
        log_on_percentage_complete(
            status, "Jungfrau data collection triggers recieved", 10
        )
        if wait:
            yield from bps.wait(JF_COMPLETE_GROUP)
        return status

    return (yield from _fly_with_unstage_contingency())


# While we should generally use device instantiation to set the path,
# this will be useful during commissioning
def override_file_name(jungfrau: CommissioningJungfrau, file_name: str):
    jungfrau.provider._filename_provider = StaticFilenameProvider(file_name)  # noqa: SLF001
    jungfrau._writer._path_info().filename = file_name  # noqa: SLF001
    yield from bps.abs_set(jungfrau._writer.file_name, file_name)  # noqa: SLF001
