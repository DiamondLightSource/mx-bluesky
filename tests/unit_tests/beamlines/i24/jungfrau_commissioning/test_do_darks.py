import asyncio
from functools import partial
from unittest.mock import AsyncMock, MagicMock, patch

import bluesky.plan_stubs as bps
from bluesky.preprocessors import run_decorator
from bluesky.run_engine import RunEngine
from ophyd_async.fastcs.jungfrau import (
    AcquisitionType,
    GainMode,
    Jungfrau,
    PedestalMode,
)
from ophyd_async.testing import set_mock_value

from mx_bluesky.beamlines.i24.jungfrau_commissioning.do_darks import do_pedestal_darks

# todo: use bps.monitor to check that gain and pedestal mode changed and changed back during test


@patch(
    "mx_bluesky.beamlines.i24.jungfrau_commissioning.do_darks.override_file_name_and_path"
)
async def test_full_do_pedestal_darks(
    mock_override_path: MagicMock, jungfrau: Jungfrau, RE: RunEngine, caplog
):
    test_path = "path"

    @run_decorator()
    def test_plan():
        status = yield from do_pedestal_darks(0.001, 2, 2, jungfrau, test_path)
        assert not status.done
        val = 0
        while not status.done:
            val += 1
            set_mock_value(jungfrau._writer._drv.num_captured, val)
            # Let status update
            yield from bps.wait_for([partial(asyncio.sleep, 0)])

    jungfrau._controller.arm = AsyncMock()
    assert await jungfrau.drv.acquisition_type.get_value() == AcquisitionType.STANDARD
    await jungfrau.drv.gain_mode.set(GainMode.FIX_G2)
    await jungfrau.drv.pedestal_mode.set(PedestalMode.OFF)

    RE(test_plan())
    assert await jungfrau.drv.acquisition_type.get_value() == AcquisitionType.STANDARD
    assert await jungfrau.drv.gain_mode.get_value() == GainMode.FIX_G2
    assert await jungfrau.drv.pedestal_mode.get_value() == PedestalMode.OFF
    mock_override_path.assert_called_once_with(jungfrau, test_path)
