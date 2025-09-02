import asyncio
from functools import partial
from unittest.mock import AsyncMock, MagicMock, patch

import bluesky.plan_stubs as bps
from bluesky.preprocessors import run_decorator
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from ophyd_async.core import AutoIncrementFilenameProvider, StaticPathProvider
from ophyd_async.fastcs.jungfrau import Jungfrau
from ophyd_async.testing import set_mock_value

from mx_bluesky.beamlines.i24.jungfrau_commissioning.do_internal_acquisition import (
    do_internal_acquisition,
)
from mx_bluesky.beamlines.i24.jungfrau_commissioning.plan_utils import JF_COMPLETE_GROUP


def test_full_do_internal_acquisition(jungfrau: Jungfrau, RE: RunEngine, caplog):
    @run_decorator()
    def test_plan():
        status = yield from do_internal_acquisition(0.001, 5, jungfrau)
        assert not status.done
        val = 0
        while not status.done:
            val += 1
            set_mock_value(jungfrau._writer._drv.num_captured, val)
            yield from bps.wait_for([partial(asyncio.sleep, 0)])
        yield from bps.wait(JF_COMPLETE_GROUP)

    jungfrau._controller.arm = AsyncMock()
    RE(test_plan())
    assert "Jungfrau data collection triggers recieved: 100%" in caplog.messages


@patch(
    "mx_bluesky.beamlines.i24.jungfrau_commissioning.plan_utils.log_on_percentage_complete"
)
def test_do_internal_acquisition_does_wait(
    mock_log_on_percent_complete: MagicMock,
    sim_run_engine: RunEngineSimulator,
    jungfrau: Jungfrau,
):
    msgs = sim_run_engine.simulate_plan(
        do_internal_acquisition(0.01, 1, jungfrau, wait=True)
    )
    assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "wait" and msg.kwargs["group"] == JF_COMPLETE_GROUP,
    )


@patch(
    "mx_bluesky.beamlines.i24.jungfrau_commissioning.plan_utils.log_on_percentage_complete"
)
def test_do_internal_acquisition_setting_path(
    mock_log_on_percent_complete: MagicMock,
    sim_run_engine: RunEngineSimulator,
    jungfrau: Jungfrau,
    tmpdir,
):
    test_path = f"{tmpdir}/test_file"
    sim_run_engine.simulate_plan(
        do_internal_acquisition(0.01, 1, jungfrau, path_of_output_file=test_path)
    )
    real_path_provider = jungfrau._writer._path_provider
    assert isinstance(real_path_provider, StaticPathProvider)
    assert isinstance(
        real_path_provider._filename_provider,
        AutoIncrementFilenameProvider,
    )
    assert real_path_provider._filename_provider._base_filename == "test_file"
    assert (real_path_provider._directory_path) == tmpdir
