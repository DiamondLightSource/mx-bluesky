from pathlib import Path
from unittest.mock import AsyncMock

import bluesky.plan_stubs as bps
import pytest
from bluesky.preprocessors import run_decorator
from bluesky.run_engine import RunEngine
from bluesky.utils import FailedStatus
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
    override_file_path,
)


async def test_fly_jungfrau(
    RE: RunEngine, jungfrau: CommissioningJungfrau, tmp_path: Path
):
    set_mock_value(jungfrau._writer.frame_counter, 10)
    mock_stop = AsyncMock()
    jungfrau.drv.acquisition_stop.trigger = mock_stop

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
            yield from bps.sleep(0.001)
        yield from bps.wait(JF_COMPLETE_GROUP)
        assert val == frames
        assert (yield from bps.rd(jungfrau._writer.file_path)) == f"{tmp_path}/00000"

    RE(_open_run_and_fly())
    assert mock_stop.await_count == 2  # once when staging, once after run complete


def test_fly_jungfrau_stops_if_exception_after_stage(
    RE: RunEngine, jungfrau: CommissioningJungfrau
):
    mock_stop = AsyncMock()
    jungfrau.drv.acquisition_stop.trigger = mock_stop
    bad_trigger_info = TriggerInfo()

    @run_decorator()
    def do_fly():
        yield from fly_jungfrau(jungfrau, bad_trigger_info)

    with pytest.raises(FailedStatus):
        RE(do_fly())
    assert mock_stop.await_count == 2  # once when staging, once on exception


async def test_override_file_path(
    jungfrau: CommissioningJungfrau, RE: RunEngine, tmp_path: Path
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
