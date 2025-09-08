from bluesky.utils import MsgGenerator
from dodal.common import inject
from ophyd_async.core import (
    WatchableAsyncStatus,
)
from ophyd_async.fastcs.jungfrau import (
    Jungfrau,
    create_jungfrau_external_triggering_info,
)
from pydantic import PositiveInt

from mx_bluesky.beamlines.i24.jungfrau_commissioning.plan_utils import (
    fly_jungfrau,
    override_file_name_and_path,
)


def do_external_acquisition(
    exp_time_s: float,
    total_triggers: PositiveInt = 1,
    period_between_frames_s: float | None = None,
    jungfrau: Jungfrau = inject("jungfrau"),
    path_of_output_file: str | None = None,
    wait: bool = False,
) -> MsgGenerator[WatchableAsyncStatus]:
    """
    Kickoff external triggering on the Jungfrau, and optionally wait for completion.

    Must be used within an open Bluesky run.

    Args:
        exp_time_s: Length of detector exposure for each frame.
        total_triggers: Number of external triggers recieved before acquisition is marked as complete.
        period_between_frames_s: Time between each detector frame, including deadtime. Not needed if frames_per_triggers is 1.
        jungfrau: Jungfrau device
        path_of_output_file: Absolute path of the detector file output, including file name. If None, then use the PathProvider
            set during jungfrau device instantiation
        wait: Optionally block until data collection is complete.
    """

    if path_of_output_file:
        override_file_name_and_path(jungfrau, path_of_output_file)

    trigger_info = create_jungfrau_external_triggering_info(total_triggers, exp_time_s)
    status = yield from fly_jungfrau(jungfrau, trigger_info, wait)
    return status
