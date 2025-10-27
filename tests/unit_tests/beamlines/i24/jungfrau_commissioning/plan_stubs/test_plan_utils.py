import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import bluesky.plan_stubs as bps
from bluesky.preprocessors import run_decorator
from bluesky.run_engine import RunEngine
from dodal.devices.i24.commissioning_jungfrau import CommissioningJungfrau
from ophyd_async.core import (
    TriggerInfo,
)
from ophyd_async.fastcs.jungfrau import GainMode
from ophyd_async.testing import (
    set_mock_value,
)

from mx_bluesky.beamlines.i24.jungfrau_commissioning.plan_stubs.plan_utils import (
    JF_COMPLETE_GROUP,
    fly_jungfrau,
    override_file_path,
)


async def test_fly_jungfrau(
    run_engine: RunEngine, jungfrau: CommissioningJungfrau, tmp_path: Path
):
    set_mock_value(jungfrau._writer.frame_counter, 10)
    mock_stop = AsyncMock()
    jungfrau.drv.acquisition_stop.trigger = mock_stop

    @run_decorator()
    def _open_run_and_fly():
        frames = 5
        status = yield from fly_jungfrau(
            jungfrau,
            TriggerInfo(livetime=1e-3, exposures_per_event=frames),
            GainMode.DYNAMIC,
        )
        val = 0
        while not status.done:
            val += 1
            set_mock_value(jungfrau._writer.frame_counter, val)
            yield from bps.sleep(0.001)
        yield from bps.wait(JF_COMPLETE_GROUP)
        assert val == frames
        assert (yield from bps.rd(jungfrau._writer.file_path)) == f"{tmp_path}/00000"

    run_engine(_open_run_and_fly())
    await asyncio.sleep(0)


async def test_override_file_path(
    jungfrau: CommissioningJungfrau, run_engine: RunEngine, tmp_path: Path
):
    new_file_name = "test_file_name"
    new_path = f"{tmp_path}/{new_file_name}"
    override_file_path(jungfrau, new_path)
    assert await jungfrau._writer.file_name.get_value() == ""
    assert await jungfrau._writer.file_path.get_value() == ""
    await jungfrau._writer.open("")
    assert await jungfrau._writer.file_name.get_value() == new_file_name
    assert await jungfrau._writer.file_path.get_value() == f"{tmp_path}/00000"
    await jungfrau._writer.open("")
    assert await jungfrau._writer.file_name.get_value() == new_file_name
    assert await jungfrau._writer.file_path.get_value() == f"{tmp_path}/00001"
