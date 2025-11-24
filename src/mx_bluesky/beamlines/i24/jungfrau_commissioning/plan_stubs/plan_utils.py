from pathlib import PurePath
from typing import cast

import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.common.watcher_utils import log_on_percentage_complete
from dodal.devices.i24.commissioning_jungfrau import CommissioningJungfrau
from ophyd_async.core import (
    AutoIncrementingPathProvider,
    StaticFilenameProvider,
    TriggerInfo,
    WatchableAsyncStatus,
)

from mx_bluesky.common.utils.log import LOGGER

JF_COMPLETE_GROUP = "JF complete"


def fly_jungfrau(
    jungfrau: CommissioningJungfrau,
    trigger_info: TriggerInfo,
    wait: bool = False,
    log_on_percentage_prefix="Jungfrau data collection triggers received",
) -> MsgGenerator[WatchableAsyncStatus]:
    """Stage, prepare, and kickoff Jungfrau with a configured TriggerInfo. Optionally wait
    for completion.

    Any plan using this stub MUST stage the Jungfrau with the stage_decorator and open a run,
    ideally using the run_decorator.

    Args:
    jungfrau: Jungfrau device.
    trigger_info: TriggerInfo which should be acquired using jungfrau util functions.
    wait: Optionally block until data collection is complete.
    log_on_percentage_prefix: String that will be appended to the "percentage completion" logging message.
    """

    LOGGER.info("Preparing detector...")
    yield from bps.prepare(jungfrau, trigger_info, wait=True)
    LOGGER.info("Detector prepared. Starting acquisition")
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


def override_file_path(jungfrau: CommissioningJungfrau, path_of_output_file: str):
    """While we should generally use device instantiation to set the path,
    during commissioning, it is useful to be able to explicitly set the filename
    and path.

    This function must be called before the Jungfrau is prepared.
    """
    _file_path = PurePath(path_of_output_file)
    _new_filename_provider = StaticFilenameProvider(_file_path.name)
    jungfrau._writer._path_info = AutoIncrementingPathProvider(  # noqa: SLF001
        _new_filename_provider, _file_path.parent
    )
