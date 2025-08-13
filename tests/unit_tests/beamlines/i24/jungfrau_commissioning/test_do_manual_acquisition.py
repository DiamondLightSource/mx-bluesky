import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import bluesky.plan_stubs as bps
from bluesky.preprocessors import run_decorator
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from ophyd_async.core import AutoIncrementFilenameProvider, StaticPathProvider
from ophyd_async.fastcs.jungfrau import Jungfrau
from ophyd_async.testing import set_mock_value

from mx_bluesky.beamlines.i24.jungfrau_commissioning.do_external_acquisition import (
    do_external_acquisition,
)


async def _do_sleep():
    await asyncio.sleep(0)


def test_full_do_external_acquisition(jungfrau: Jungfrau, RE: RunEngine, caplog):
    @run_decorator()
    def test_plan():
        status = yield from do_external_acquisition(0.001, 0.002, 5, 5, jungfrau)
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


@patch(
    "mx_bluesky.beamlines.i24.jungfrau_commissioning.do_external_acquisition.log_on_percentage_complete"
)
def test_do_external_acquisition_does_wait(
    mock_log_on_percent_complete: MagicMock,
    sim_run_engine: RunEngineSimulator,
    jungfrau: Jungfrau,
):
    msgs = sim_run_engine.simulate_plan(
        do_external_acquisition(0.01, 0.02, 1, 1, jungfrau, wait=True)
    )
    assert_message_and_return_remaining(
        msgs, lambda msg: msg.command == "wait" and msg.kwargs["group"] == "jf_complete"
    )


@patch(
    "mx_bluesky.beamlines.i24.jungfrau_commissioning.do_external_acquisition.log_on_percentage_complete"
)
def test_do_external_acquisition_setting_path(
    mock_log_on_percent_complete: MagicMock,
    sim_run_engine: RunEngineSimulator,
    jungfrau: Jungfrau,
    tmpdir,
):
    test_path = f"{tmpdir}/test_file"
    sim_run_engine.simulate_plan(
        do_external_acquisition(
            0.01, 0.02, 1, 1, jungfrau, path_of_output_file=test_path
        )
    )
    real_path_provider = jungfrau._writer._path_provider
    assert isinstance(real_path_provider, StaticPathProvider)
    assert isinstance(
        real_path_provider._filename_provider,
        AutoIncrementFilenameProvider,
    )
    assert real_path_provider._filename_provider._base_filename == "test_file"
    assert (real_path_provider._directory_path) == tmpdir
