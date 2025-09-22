from bluesky.utils import MsgGenerator
from dodal.common import inject
from dodal.devices.i24.commissioning_jungfrau import CommissioningJungfrau
from ophyd_async.core import (
    WatchableAsyncStatus,
)
from ophyd_async.fastcs.jungfrau import (
    create_jungfrau_external_triggering_info,
)
from pydantic import PositiveInt

from mx_bluesky.beamlines.i24.jungfrau_commissioning.plan_utils import (
    fly_jungfrau,
    override_file_name,
)


def do_external_acquisition(
    exp_time_s: float,
    total_triggers: PositiveInt = 1,
    output_file_name: str | None = None,
    wait: bool = False,
    jungfrau: CommissioningJungfrau = inject("commissioning_jungfrau"),
) -> MsgGenerator[WatchableAsyncStatus]:
    """
    Kickoff external triggering on the Jungfrau, and optionally wait for completion.

    Must be used within an open Bluesky run.

    Args:
        exp_time_s: Length of detector exposure for each frame.
        total_triggers: Number of external triggers recieved before acquisition is marked as complete.
        jungfrau: Jungfrau device
        output_file_name: Absolute path of the detector file output, including file name. If None, then use the PathProvider
            set during jungfrau device instantiation
        wait: Optionally block until data collection is complete.
    """

    if output_file_name:
        override_file_name(jungfrau, output_file_name)

    trigger_info = create_jungfrau_external_triggering_info(total_triggers, exp_time_s)
    status = yield from fly_jungfrau(jungfrau, trigger_info, wait)
    return status
