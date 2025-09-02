from pathlib import Path
from typing import cast

import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.common.watcher_utils import log_on_percentage_complete
from ophyd_async.core import (
    AutoIncrementFilenameProvider,
    StaticPathProvider,
    TriggerInfo,
    WatchableAsyncStatus,
)
from ophyd_async.fastcs.jungfrau import (
    Jungfrau,
)

from mx_bluesky.common.utils.log import LOGGER

JF_PREPARE_GROUP = "JF prepare"
JF_COMPLETE_GROUP = "JF complete"


def fly_jungfrau(
    jungfrau: Jungfrau,
    trigger_info: TriggerInfo,
    wait: bool = False,
    log_on_percentage_message: str = "Jungfrau data collection triggers recieved",
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
    yield from bps.prepare(jungfrau, trigger_info, group=JF_PREPARE_GROUP)
    yield from bps.wait(group=JF_PREPARE_GROUP)
    LOGGER.info("Detector prepared. Starting acquisition")
    yield from bps.kickoff(jungfrau, wait=True)
    LOGGER.info("Waiting for acquisition to complete...")
    status = yield from bps.complete(jungfrau, group=JF_COMPLETE_GROUP)

    # StandardDetector.complete converts regular status to watchable status,
    # but bluesky plan stubs can't see this currently
    status = cast(WatchableAsyncStatus, status)
    log_on_percentage_complete(status, log_on_percentage_message, 10)
    if wait:
        yield from bps.wait(JF_COMPLETE_GROUP)
    return status


# While we should generally use device instantiation to set the path,
# this will be useful during commissioning
def override_file_name_and_path(jungfrau: Jungfrau, path_of_output_file: str):
    _file_path = Path(path_of_output_file)
    filename_provider = AutoIncrementFilenameProvider(_file_path.name)
    path_provider = StaticPathProvider(filename_provider, _file_path.parent)
    jungfrau._writer._path_provider = path_provider  # noqa: SLF001
