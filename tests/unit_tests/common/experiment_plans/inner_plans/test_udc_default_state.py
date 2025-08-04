from unittest.mock import MagicMock

import pytest
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from dodal.devices.aperturescatterguard import ApertureScatterguard, ApertureValue
from dodal.devices.cryostream import CryoStream
from dodal.devices.scintillator import InOut, Scintillator
from ophyd_async.core import init_devices

from mx_bluesky.common.experiment_plans.inner_plans.udc_default_state import (
    UDCDefaultDevices,
    move_to_udc_default_state,
)


async def test_given_cryostream_temp_is_too_high_then_exception_raised(
    RE: RunEngine,
    sim_run_engine: RunEngineSimulator,
):
    devices: UDCDefaultDevices = MagicMock()
    async with init_devices(mock=True):
        devices.cryostream = CryoStream(prefix="")
    sim_run_engine.add_read_handler_for(
        devices.cryostream.temperature_k, devices.cryostream.MAX_TEMP_K + 10
    )
    with pytest.raises(ValueError, match="temperature is too high"):
        sim_run_engine.simulate_plan(move_to_udc_default_state(devices))


async def test_given_cryostream_pressure_is_too_high_then_exception_raised(
    RE: RunEngine,
    sim_run_engine: RunEngineSimulator,
):
    devices: UDCDefaultDevices = MagicMock()
    async with init_devices(mock=True):
        devices.cryostream = CryoStream(prefix="")
    sim_run_engine.add_read_handler_for(
        devices.cryostream.back_pressure_bar, devices.cryostream.MAX_PRESSURE_BAR + 10
    )
    with pytest.raises(ValueError, match = "pressure is too high"):
        sim_run_engine.simulate_plan(move_to_udc_default_state(devices))


async def test_scintillator_is_moved_out_before_aperture_scatterguard_moved_in(
    RE: RunEngine,
    sim_run_engine: RunEngineSimulator,
):
    devices: UDCDefaultDevices = MagicMock()
    async with init_devices(mock=True):
        devices.cryostream = CryoStream(prefix="")
        devices.aperture_scatterguard = ApertureScatterguard(
            MagicMock(), MagicMock(), name="ap_sg"
        )
        devices.scintillator = Scintillator("", MagicMock(), MagicMock(), name="scin")

    msgs = sim_run_engine.simulate_plan(move_to_udc_default_state(devices))

    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "scin-selected_pos"
        and msg.args[0] == InOut.OUT,
    )
    msgs = assert_message_and_return_remaining(msgs, lambda msg: msg.command == "wait")
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "ap_sg-selected_aperture"
        and msg.args[0] == ApertureValue.SMALL,
    )
