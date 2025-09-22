import asyncio
from functools import partial
from pathlib import Path

import bluesky.plan_stubs as bps
from bluesky.preprocessors import run_decorator
from bluesky.run_engine import RunEngine
from dodal.devices.i24.commissioning_jungfrau import CommissioningJungfrau
from ophyd_async.core import (
    TriggerInfo,
)
from ophyd_async.testing import (
    set_mock_value,
)

from mx_bluesky.beamlines.i24.jungfrau_commissioning.plan_utils import (
    JF_COMPLETE_GROUP,
    fly_jungfrau,
    override_file_name,
)


def test_fly_jungfrau(RE: RunEngine, jungfrau: CommissioningJungfrau, tmp_path: Path):
    set_mock_value(jungfrau._writer.frame_counter, 10)

    @run_decorator()
    def _open_run_and_fly():
        frames = 5
        status = yield from fly_jungfrau(
            jungfrau, TriggerInfo(livetime=1e-3, exposures_per_event=frames)
        )
        val = 0
        while not status.done:
            val += 1
            set_mock_value(jungfrau._writer.frame_counter, val)
            yield from bps.wait_for([partial(asyncio.sleep, 0)])
        yield from bps.wait(JF_COMPLETE_GROUP)
        assert val == frames
        assert (yield from bps.rd(jungfrau._writer.file_path)) == f"{tmp_path}/00001"

    RE(_open_run_and_fly())


async def test_override_file_name(jungfrau: CommissioningJungfrau, RE: RunEngine):
    new_file_name = "test_file_name"
    RE(override_file_name(jungfrau, new_file_name))
    assert await jungfrau._writer.file_name.get_value() == new_file_name
