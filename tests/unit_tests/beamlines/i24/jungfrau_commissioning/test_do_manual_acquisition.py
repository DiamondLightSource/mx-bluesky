import asyncio
from unittest.mock import AsyncMock

import bluesky.plan_stubs as bps
from bluesky.preprocessors import run_decorator
from bluesky.run_engine import RunEngine
from ophyd_async.fastcs.jungfrau import Jungfrau
from ophyd_async.testing import set_mock_value

from mx_bluesky.beamlines.i24.jungfrau_commissioning.do_manual_acquisition import (
    do_manual_acquisition,
)


async def _do_sleep():
    await asyncio.sleep(0)


def test_full_do_manual_acquisition(jungfrau: Jungfrau, RE: RunEngine, caplog):
    @run_decorator()
    def test_plan():
        status = yield from do_manual_acquisition(0.001, 0.002, 5, 5, jungfrau)
        assert not status.done
        val = 0
        while not status.done:
            val += 1
            set_mock_value(jungfrau._writer._drv.num_captured, val)

            # Let status update
            yield from bps.wait_for([_do_sleep])
        yield from bps.wait("jf_complete")

    jungfrau._controller.arm = AsyncMock()
    RE(test_plan())
    for i in range(20, 120, 20):
        assert f"Jungfrau data collection triggers recieved: {i}%" in caplog.messages
    print(caplog)
