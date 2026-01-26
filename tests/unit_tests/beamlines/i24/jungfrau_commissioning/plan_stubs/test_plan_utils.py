import asyncio
from functools import partial
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

import bluesky.plan_stubs as bps
from bluesky.preprocessors import run_decorator
from bluesky.run_engine import RunEngine
from dodal.devices.i24.commissioning_jungfrau import CommissioningJungfrau
from ophyd_async.core import (
    TriggerInfo,
    completed_status,
    set_mock_value,
)
from ophyd_async.fastcs.jungfrau import GainMode

from mx_bluesky.beamlines.i24.jungfrau_commissioning.plan_stubs.plan_utils import (
    JF_COMPLETE_GROUP,
    fly_jungfrau,
)


async def test_fly_jungfrau(
    run_engine: RunEngine, jungfrau: CommissioningJungfrau, tmp_path: Path
):
    set_mock_value(jungfrau._writer.frame_counter, 10)
    mock_stop = AsyncMock()
    jungfrau.drv.acquisition_stop.trigger = mock_stop

    filename = "test"

    @run_decorator(md={"detector_file_template": filename})
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
        assert (
            yield from bps.rd(jungfrau._writer.file_path)
        ) == f"{tmp_path}/0000_{filename}"

    run_engine(_open_run_and_fly())
    await asyncio.sleep(0)


@patch(
    "mx_bluesky.beamlines.i24.jungfrau_commissioning.plan_stubs.plan_utils.log_on_percentage_complete",
    new=MagicMock(),
)
async def test_fly_jungfrau_does_read_plan_after_prepare(
    run_engine: RunEngine, jungfrau: CommissioningJungfrau
):
    mock_stop = AsyncMock()
    jungfrau.drv.acquisition_stop.trigger = mock_stop

    read_hardware = MagicMock()

    filename = "test"
    jungfrau.prepare = MagicMock(side_effect=lambda _: completed_status())

    parent_mock = MagicMock()
    parent_mock.attach_mock(jungfrau.prepare, "jungfrau_prepare")
    parent_mock.attach_mock(read_hardware, "read_hardware")
    jungfrau.kickoff = MagicMock(side_effect=lambda: completed_status())
    jungfrau.complete = MagicMock(side_effect=lambda: completed_status())
    test_trigger_info = TriggerInfo(livetime=1e-3, exposures_per_event=5)

    @run_decorator(md={"detector_file_template": filename})
    def fly_in_run():
        yield from fly_jungfrau(
            jungfrau,
            test_trigger_info,
            GainMode.DYNAMIC,
            read_hardware_after_prepare_plan=partial(read_hardware),
        )

    run_engine(fly_in_run())
    assert parent_mock.method_calls == [
        call.jungfrau_prepare(test_trigger_info),
        call.read_hardware(),
    ]
