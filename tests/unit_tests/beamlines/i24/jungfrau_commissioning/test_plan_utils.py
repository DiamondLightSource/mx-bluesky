import asyncio
from functools import partial
from pathlib import Path, PurePath

import bluesky.plan_stubs as bps
import pytest
from bluesky.preprocessors import run_decorator
from bluesky.run_engine import RunEngine
from dodal.devices.i24.commissioning_jungfrau import CommissioningJungfrau
from ophyd_async.core import (
    AutoIncrementingPathProvider,
    StaticFilenameProvider,
    TriggerInfo,
    init_devices,
)
from ophyd_async.testing import (
    set_mock_value,
)

from mx_bluesky.beamlines.i24.jungfrau_commissioning.plan_utils import (
    JF_COMPLETE_GROUP,
    fly_jungfrau,
)

JF_FILENAME = "jf_out"


@pytest.fixture
def jungfrau(tmpdir: Path) -> CommissioningJungfrau:
    with init_devices(mock=True):
        name = StaticFilenameProvider(JF_FILENAME)
        path = AutoIncrementingPathProvider(name, PurePath(tmpdir))
        detector = CommissioningJungfrau("", "", path)

    return detector


def test_fly_jungfrau(jungfrau: CommissioningJungfrau, RE: RunEngine, tmpdir: Path):
    set_mock_value(jungfrau._writer.writer_ready, 1)
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
        assert (yield from bps.rd(jungfrau._writer.file_path)) == tmpdir
        assert (yield from bps.rd(jungfrau._writer.file_name)) == JF_FILENAME

    RE(_open_run_and_fly())
