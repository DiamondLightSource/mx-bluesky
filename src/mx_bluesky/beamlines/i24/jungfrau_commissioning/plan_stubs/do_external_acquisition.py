from bluesky.utils import MsgGenerator
from dodal.common import inject
from dodal.devices.i24.commissioning_jungfrau import CommissioningJungfrau
from ophyd_async.core import (
    WatchableAsyncStatus,
)
from ophyd_async.fastcs.jungfrau import (
    GainMode,
    create_jungfrau_external_triggering_info,
)
from pydantic import PositiveInt

from mx_bluesky.beamlines.i24.jungfrau_commissioning.plan_stubs.plan_utils import (
    fly_jungfrau,
)


def do_external_acquisition(
    exp_time_s: float,
    gain_mode: GainMode,
    total_triggers: PositiveInt = 1,
    wait: bool = False,
    jungfrau: CommissioningJungfrau = inject("commissioning_jungfrau"),
) -> MsgGenerator[WatchableAsyncStatus]:
    """
    Kickoff external triggering on the Jungfrau, and optionally wait for completion.

    Any plan using this stub MUST stage the Jungfrau with the stage_decorator and open a run,
    ideally using the run_decorator.

    Args:
        exp_time_s: Length of detector exposure for each frame.
        total_triggers: Number of external triggers received before acquisition is marked as complete.
        jungfrau: Jungfrau device
        wait: Optionally block until data collection is complete.
    """

    trigger_info = create_jungfrau_external_triggering_info(total_triggers, exp_time_s)
    status = yield from fly_jungfrau(jungfrau, trigger_info, gain_mode, wait=wait)
    return status
