from pathlib import Path
from typing import cast

import bluesky.plan_stubs as bps
from dodal.common import inject
from dodal.common.watcher_utils import log_on_percentage_complete
from ophyd_async.core import (
    AutoIncrementFilenameProvider,
    StaticPathProvider,
    WatchableAsyncStatus,
)
from ophyd_async.fastcs.jungfrau import (
    Jungfrau,
    create_jungfrau_external_triggering_info,
)

from mx_bluesky.common.utils.log import LOGGER


def do_internal_acquisition(
    exp_time_s: float,
    period_between_frames_s: float,
    frames_per_trigger: int = 1,
    total_triggers: int = 1,
    jungfrau: Jungfrau = inject("jungfrau"),
    path_of_output_file: str | None = None,
    wait: bool = False,
):
    """
    Kickoff internal triggering on the Jungfrau, and optionally wait for completion.

    Must be used within an open Bluesky run.

    Args:
        exp_time_s: Length of detector exposure for each frame
        period_between_frames_s: Time between each detector frame, including deadtime
        frames_per_trigger: Number of frames for each external trigger
        total_triggers: Number of external triggers recieved before acquisition is marked as complete
        jungfrau: Jungfrau device
        path_of_output_file: Absolute path of the detector file output, including file name. If None, then use the PathProvider
            set during jungfrau device instantiation
    """

    # While we should generally use device instantiation to set the path,
    # this will be useful during commissioning
    if path_of_output_file:
        _file_path = Path(path_of_output_file)
        filename_provider = AutoIncrementFilenameProvider(_file_path.name)
        path_provider = StaticPathProvider(filename_provider, _file_path.parent)
        jungfrau._writer._path_provider = path_provider  # noqa: SLF001

    trigger_info = create_jungfrau_external_triggering_info(
        total_triggers, frames_per_trigger, exp_time_s, period_between_frames_s
    )
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
