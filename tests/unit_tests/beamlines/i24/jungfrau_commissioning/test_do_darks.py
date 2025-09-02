import asyncio
from functools import partial
from unittest.mock import AsyncMock, MagicMock, patch

import bluesky.plan_stubs as bps
from bluesky.callbacks import CallbackBase
from bluesky.preprocessors import monitor_during_wrapper, run_decorator
from bluesky.run_engine import RunEngine
from ophyd_async.fastcs.jungfrau import (
    AcquisitionType,
    GainMode,
    Jungfrau,
    PedestalMode,
)
from ophyd_async.testing import set_mock_value

from mx_bluesky.beamlines.i24.jungfrau_commissioning.do_darks import do_pedestal_darks


class CheckMonitor(CallbackBase):
    def __init__(self, signals_to_track: list[str]):
        self.signals_and_values = {signal: [] for signal in signals_to_track}

    def event(self, doc):
        key, value = next(iter(doc["data"].items()))
        self.signals_and_values[key].append(value)
        return doc


@patch(
    "mx_bluesky.beamlines.i24.jungfrau_commissioning.do_darks.override_file_name_and_path"
)
async def test_full_do_pedestal_darks(
    mock_override_path: MagicMock, jungfrau: Jungfrau, RE: RunEngine, caplog
):
    # Test plan succeeds in RunEngine and pedestal-specific signals are changed as expected
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
    monitor_tracker = CheckMonitor(
        [
            "jungfrau-drv-acquisition_type",
            "jungfrau-drv-gain_mode",
            "jungfrau-drv-pedestal_mode",
        ]
    )
    RE.subscribe(monitor_tracker)
    RE(
        monitor_during_wrapper(
            test_plan(),
            [
                jungfrau.drv.acquisition_type,
                jungfrau.drv.gain_mode,
                jungfrau.drv.pedestal_mode,
            ],
        )
    )
    assert monitor_tracker.signals_and_values["jungfrau-drv-acquisition_type"] == [
        AcquisitionType.STANDARD,
        AcquisitionType.PEDESTAL,
        AcquisitionType.STANDARD,
    ]
    assert monitor_tracker.signals_and_values["jungfrau-drv-gain_mode"] == [
        GainMode.FIX_G2,
        GainMode.DYNAMIC,
        GainMode.FIX_G2,
    ]
    assert monitor_tracker.signals_and_values["jungfrau-drv-pedestal_mode"] == [
        PedestalMode.OFF,
        PedestalMode.ON,
        PedestalMode.OFF,
    ]
    mock_override_path.assert_called_once_with(jungfrau, test_path)
