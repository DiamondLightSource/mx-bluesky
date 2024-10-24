import bluesky.plan_stubs as bps
import pytest
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from dodal.beamlines.i03 import eiger
from dodal.devices.eiger import EigerDetector

from mx_bluesky.common.device_setup_plans.read_hardware_for_setup import (
    read_hardware_for_zocalo,
)


@pytest.fixture
def fake_eiger() -> EigerDetector:
    return eiger(fake_with_ophyd_sim=True)


def test_read_hardware_for_zocalo_in_RE(fake_eiger, RE: RunEngine):
    def open_run_and_read_hardware():
        yield from bps.open_run()
        yield from read_hardware_for_zocalo(fake_eiger)

    RE(open_run_and_read_hardware())


def test_read_hardware_correct_messages(fake_eiger, sim_run_engine: RunEngineSimulator):
    msgs = sim_run_engine.simulate_plan(read_hardware_for_zocalo(fake_eiger))
    msgs = assert_message_and_return_remaining(
        msgs, lambda msg: msg.command == "create"
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "read"
        and msg.obj.name == "eiger_odin_file_writer_id",
    )
    msgs = assert_message_and_return_remaining(msgs, lambda msg: msg.command == "save")
