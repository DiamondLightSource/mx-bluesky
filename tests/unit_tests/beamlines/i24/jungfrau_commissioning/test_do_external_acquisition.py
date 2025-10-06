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

from mx_bluesky.beamlines.i24.jungfrau_commissioning.do_external_acquisition import (
    do_external_acquisition,
)
from mx_bluesky.beamlines.i24.jungfrau_commissioning.plan_utils import JF_COMPLETE_GROUP


def test_full_do_external_acquisition(
    jungfrau: CommissioningJungfrau, RE: RunEngine, caplog
):
    @run_decorator()
    def test_plan():
        status = yield from do_external_acquisition(
            0.001, GainMode.DYNAMIC, 5, jungfrau=jungfrau
        )
        assert not status.done
        val = 0
        while not status.done:
            val += 1
            set_mock_value(jungfrau._writer.frame_counter, val)

            # Let status update
            yield from bps.wait_for([partial(asyncio.sleep, 0)])
        yield from bps.wait(JF_COMPLETE_GROUP)

    jungfrau._controller.arm = AsyncMock()
    RE(test_plan())
    for i in range(20, 120, 20):
        assert f"Jungfrau data collection triggers recieved: {i}%" in caplog.messages


@patch(
    "mx_bluesky.beamlines.i24.jungfrau_commissioning.plan_utils.log_on_percentage_complete"
)
def test_do_external_acquisition_does_wait(
    mock_log_on_percent_complete: MagicMock,
    sim_run_engine: RunEngineSimulator,
    RE: RunEngine,
    jungfrau: CommissioningJungfrau,
):
    msgs = sim_run_engine.simulate_plan(
        do_external_acquisition(0.01, GainMode.DYNAMIC, 1, wait=True, jungfrau=jungfrau)
    )
    assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "wait" and msg.kwargs["group"] == JF_COMPLETE_GROUP,
    )
