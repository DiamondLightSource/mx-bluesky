import asyncio
from functools import partial
from unittest.mock import AsyncMock, MagicMock, patch

import bluesky.plan_stubs as bps
from bluesky.preprocessors import run_decorator
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from dodal.beamlines.i24 import CommissioningJungfrau
from ophyd_async.fastcs.jungfrau import GainMode
from ophyd_async.testing import set_mock_value

from mx_bluesky.beamlines.i24.jungfrau_commissioning.plan_stubs.do_internal_acquisition import (
    do_internal_acquisition,
)
from mx_bluesky.beamlines.i24.jungfrau_commissioning.plan_stubs.plan_utils import (
    JF_COMPLETE_GROUP,
)


def test_full_do_internal_acquisition(
    RE: RunEngine, jungfrau: CommissioningJungfrau, caplog
):
    @run_decorator()
    def test_plan():
        status = yield from do_internal_acquisition(
            0.001, GainMode.DYNAMIC, 5, jungfrau=jungfrau
        )
        assert not status.done
        val = 0
        while not status.done:
            val += 1
            set_mock_value(jungfrau._writer.frame_counter, val)
            yield from bps.wait_for([partial(asyncio.sleep, 0)])
        yield from bps.wait(JF_COMPLETE_GROUP)

    jungfrau._controller.arm = AsyncMock()
    RE(test_plan())
    assert "Jungfrau data collection triggers recieved: 100%" in caplog.messages


@patch(
    "mx_bluesky.beamlines.i24.jungfrau_commissioning.plan_stubs.plan_utils.log_on_percentage_complete",
    new=MagicMock(),
)
def test_do_internal_acquisition_does_wait(
    sim_run_engine: RunEngineSimulator,
    jungfrau: CommissioningJungfrau,
):
    msgs = sim_run_engine.simulate_plan(
        do_internal_acquisition(0.01, GainMode.DYNAMIC, 1, jungfrau, wait=True)
    )
    assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "wait" and msg.kwargs["group"] == JF_COMPLETE_GROUP,
    )
