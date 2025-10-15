from unittest.mock import AsyncMock, MagicMock, call, patch

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
import pytest
from bluesky.callbacks import CallbackBase
from bluesky.run_engine import RunEngine
from dodal.devices.i24.commissioning_jungfrau import CommissioningJungfrau
from ophyd_async.core import completed_status
from ophyd_async.fastcs.jungfrau import (
    AcquisitionType,
    GainMode,
    PedestalMode,
)

from mx_bluesky.beamlines.i24.jungfrau_commissioning.do_darks import (
    do_pedestal_darks,
)


class CheckMonitor(CallbackBase):
    """Store the order and values of updates to specified signals

    Usage: Instantiate this callback with list of signals to track, and subscribe the RE to this
    callback. Run your plan using Bluesky's monitor_during decorator or wrapper, specifing the same signals
    in the monitor.
    """

    def __init__(self, signals_to_track: list[str]):
        self.signals_and_values = {signal: [] for signal in signals_to_track}

    def event(self, doc):
        key, value = next(iter(doc["data"].items()))
        # don't record a value changing to the same value
        if (
            not len(self.signals_and_values[key])
            or not self.signals_and_values[key][-1] == value
        ):
            self.signals_and_values[key].append(value)
        return doc


def fake_complete(_, group=None):
    yield from bps.null()
    return completed_status()


@patch(
    "mx_bluesky.beamlines.i24.jungfrau_commissioning.plan_utils.log_on_percentage_complete",
    new=MagicMock,
)
@patch(
    "mx_bluesky.beamlines.i24.jungfrau_commissioning.plan_utils.bps.complete",
    new=MagicMock(side_effect=fake_complete),
)
@patch("mx_bluesky.beamlines.i24.jungfrau_commissioning.do_darks.override_file_path")
async def test_full_do_pedestal_darks(
    mock_override_path: MagicMock, jungfrau: CommissioningJungfrau, RE: RunEngine
):
    # Test that plan succeeds in RunEngine and pedestal-specific signals are changed as expected
    test_path = "path"

    @bpp.run_decorator(
        md={
            "metadata": {"sample_id": "blah"},
            "activate_callbacks": ["SampleHandlingCallback"],
        }
    )
    def test_plan():
        yield from bps.monitor(jungfrau.drv.acquisition_type, name="AT")
        yield from bps.monitor(jungfrau.drv.pedestal_mode_state, name="PM")
        yield from bps.monitor(jungfrau.drv.gain_mode, name="GM")
        yield from do_pedestal_darks(0.001, 2, 2, jungfrau, test_path)

    jungfrau._controller.arm = AsyncMock()
    assert await jungfrau.drv.acquisition_type.get_value() == AcquisitionType.STANDARD
    await jungfrau.drv.gain_mode.set(GainMode.FIX_G2)
    await jungfrau.drv.pedestal_mode_state.set(PedestalMode.OFF)
    monitor_tracker = CheckMonitor(
        [
            "detector-drv-acquisition_type",
            "detector-drv-pedestal_mode_state",
            "detector-drv-gain_mode",
        ]
    )
    RE.subscribe(monitor_tracker)
    RE(test_plan())

    assert monitor_tracker.signals_and_values["detector-drv-acquisition_type"] == [
        AcquisitionType.STANDARD,
        AcquisitionType.PEDESTAL,
        AcquisitionType.STANDARD,
    ]
    assert monitor_tracker.signals_and_values["detector-drv-pedestal_mode_state"] == [
        PedestalMode.OFF,
        PedestalMode.ON,
        PedestalMode.OFF,
    ]

    # When using the real detector, the switching of gain mode is a bit more complicated,
    # see the docstring for the do_pedestal_darks plan.
    assert monitor_tracker.signals_and_values["detector-drv-gain_mode"] == [
        GainMode.FIX_G2,
        GainMode.DYNAMIC,
    ]
    mock_override_path.assert_called_once_with(jungfrau, test_path)


class FakeException(Exception): ...


@patch("mx_bluesky.beamlines.i24.jungfrau_commissioning.do_darks.override_file_path")
@patch("bluesky.plan_stubs.unstage")
async def test_pedestals_unstage_and_wait_on_exception(
    mock_unstage: MagicMock,
    mock_override_path: MagicMock,
    jungfrau: CommissioningJungfrau,
    RE: RunEngine,
):
    jungfrau.stage = MagicMock(side_effect=FakeException)

    def test_plan():
        yield from do_pedestal_darks(0.001, 2, 2, jungfrau)

    with pytest.raises(FakeException):
        RE(test_plan())

    assert mock_unstage.call_count == 2  # Once on stage, once on unstage
    assert [c == call(jungfrau, wait=True) for c in mock_unstage.call_args_list]
