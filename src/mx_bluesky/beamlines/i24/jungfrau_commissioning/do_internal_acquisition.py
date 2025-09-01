from pathlib import Path

from bluesky.utils import MsgGenerator
from dodal.common import inject
from ophyd_async.core import (
    AutoIncrementFilenameProvider,
    StaticPathProvider,
    WatchableAsyncStatus,
)
from ophyd_async.fastcs.jungfrau import (
    Jungfrau,
    create_jungfrau_internal_triggering_info,
)
from pydantic import PositiveInt

from mx_bluesky.beamlines.i24.jungfrau_commissioning.plan_utils import fly_jungfrau


def do_internal_acquisition(
    exp_time_s: float,
    total_frames: PositiveInt = 1,
    jungfrau: Jungfrau = inject("jungfrau"),
    path_of_output_file: str | None = None,
    wait: bool = False,
) -> MsgGenerator[WatchableAsyncStatus]:
    """
    Kickoff internal triggering on the Jungfrau, and optionally wait for completion. Frames
    per trigger will trigger as rapidly as possible according to the Jungfrau deadtime.

    Must be used within an open Bluesky run.

    Args:
        exp_time_s: Length of detector exposure for each frame.
        total_frames: Number of frames taken after being internally triggered.
        period_between_frames_s: Time between each detector frame, including deadtime. Not needed if frames_per_triggers is 1.
        jungfrau: Jungfrau device
        path_of_output_file: Absolute path of the detector file output, including file name. If None, then use the PathProvider
            set during jungfrau device instantiation
        wait: Optionally block until data collection is complete.
    """

    # While we should generally use device instantiation to set the path,
    # this will be useful during commissioning
    if path_of_output_file:
        _file_path = Path(path_of_output_file)
        filename_provider = AutoIncrementFilenameProvider(_file_path.name)
        path_provider = StaticPathProvider(filename_provider, _file_path.parent)
        jungfrau._writer._path_provider = path_provider  # noqa: SLF001

    trigger_info = create_jungfrau_internal_triggering_info(total_frames, exp_time_s)
    status = yield from fly_jungfrau(jungfrau, trigger_info, wait)
    return status
