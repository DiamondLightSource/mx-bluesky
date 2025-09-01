import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.common import inject
from ophyd_async.core import (
    WatchableAsyncStatus,
)
from ophyd_async.fastcs.jungfrau import (
    AcquisitionType,
    Jungfrau,
    create_jungfrau_pedestal_triggering_info,
)
from pydantic import PositiveInt

from mx_bluesky.beamlines.i24.jungfrau_commissioning.plan_utils import fly_jungfrau


def do_pedestal_darks(
    exp_time_s: float,
    pedestal_frames: PositiveInt = 1,
    pedestal_loops: PositiveInt = 1,
    period_between_frames_s: float | None = None,
    jungfrau: Jungfrau = inject("jungfrau"),
    path_of_output_file: str | None = None,
    wait: bool = False,
) -> MsgGenerator[WatchableAsyncStatus]:
    yield from bps.abs_set(
        jungfrau.drv.acquisition_type, AcquisitionType.PEDESTAL, wait=True
    )
    trigger_info = create_jungfrau_pedestal_triggering_info(
        exp_time_s, pedestal_frames, pedestal_loops
    )
    status = yield from fly_jungfrau(jungfrau, trigger_info, wait)
    return status
