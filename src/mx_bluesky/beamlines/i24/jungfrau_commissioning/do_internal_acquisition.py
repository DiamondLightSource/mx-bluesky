from bluesky.utils import MsgGenerator
from dodal.beamlines.i24 import CommissioningJungfrau
from dodal.common import inject
from ophyd_async.core import (
    WatchableAsyncStatus,
)
from ophyd_async.fastcs.jungfrau import (
    create_jungfrau_internal_triggering_info,
)
from pydantic import PositiveInt

from mx_bluesky.beamlines.i24.jungfrau_commissioning.plan_utils import (
    fly_jungfrau,
    override_file_path,
)


def do_internal_acquisition(
    exp_time_s: float,
    total_frames: PositiveInt = 1,
    jungfrau: CommissioningJungfrau = inject("jungfrau"),
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

    if path_of_output_file:
        override_file_path(jungfrau, path_of_output_file)

    trigger_info = create_jungfrau_internal_triggering_info(total_frames, exp_time_s)
    status = yield from fly_jungfrau(jungfrau, trigger_info, wait=wait)
    return status
