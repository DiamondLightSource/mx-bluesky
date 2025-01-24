from unittest.mock import MagicMock, patch

from bluesky.run_engine import RunEngine
from dodal.devices.i24.jungfrau import GainMode, JungFrau1M
from ophyd_async.testing import get_mock

from mx_bluesky.beamlines.i24.jungfrau_commissioning.plans.gain_mode_darks_plans import (
    do_manual_acquisition,
    set_gain_mode,
)


@patch(
    "bluesky.plan_stubs.wait",
)
async def test_set_gain_mode(
    bps_wait: MagicMock,
    fake_devices,
    RE: RunEngine,
):
    jungfrau: JungFrau1M = fake_devices["jungfrau"]

    RE(set_gain_mode(jungfrau, GainMode.DYNAMIC))
    assert await jungfrau.gain_mode.get_value() == "dynamic"
    RE(set_gain_mode(jungfrau, GainMode.FORCESWITCHG1))
    assert await jungfrau.gain_mode.get_value() == "forceswitchg1"
    RE(set_gain_mode(jungfrau, GainMode.FORCESWITCHG2))
    assert await jungfrau.gain_mode.get_value() == "forceswitchg2"


@patch(
    "bluesky.plan_stubs.wait",
)
def test_do_dark_acq(
    bps_wait: MagicMock,
    fake_devices,
    RE: RunEngine,
):
    # gonio: VGonio = fake_devices["gonio"]
    # zebra: Zebra = fake_devices["zebra"]
    jungfrau: JungFrau1M = fake_devices["jungfrau"]

    RE(do_manual_acquisition(jungfrau, 0.001, 0.001, 1000))
    acquire_mock = get_mock(jungfrau.acquire_start)
    acquire_mock.set.assert_called()  # type: ignore
