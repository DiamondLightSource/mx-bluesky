from unittest.mock import patch

import pytest
from blueapi.core import MsgGenerator
from bluesky import plan_stubs as bps
from bluesky.plan_stubs import null
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from dodal.beamlines.i03 import eiger
from dodal.devices.fast_grid_scan import ZebraFastGridScan
from dodal.devices.synchrotron import Synchrotron, SynchrotronMode
from ophyd_async.core import DeviceCollector, set_mock_value

from mx_bluesky.common.plan_stubs.do_fgs import do_fgs


@pytest.fixture
def fgs_devices(RE):
    with DeviceCollector(mock=True):
        synchrotron = Synchrotron()
        grid_scan_device = ZebraFastGridScan("zebra_fgs")

    # Eiger done separately as not ophyd-async yet
    detector = eiger(fake_with_ophyd_sim=True)

    return {
        "synchrotron": synchrotron,
        "grid_scan_device": grid_scan_device,
        "detector": detector,
    }


def test_do_fgs_correct_messages(sim_run_engine: RunEngineSimulator, fgs_devices):
    def null_plan() -> MsgGenerator:
        yield from null()

    synchrotron = fgs_devices["synchrotron"]
    detector = fgs_devices["detector"]
    fgs_device = fgs_devices["grid_scan_device"]
    with (
        patch(
            "mx_bluesky.common.plan_stubs.do_fgs.check_topup_and_wait_if_necessary"
        ) as mock_check_topup,
        patch(
            "mx_bluesky.common.plan_stubs.do_fgs.read_hardware_for_zocalo"
        ) as mock_read_hardware,
    ):
        msgs = sim_run_engine.simulate_plan(
            do_fgs(
                fgs_device,
                detector,
                synchrotron,
                during_collection_plan=null_plan(),
            )
        )

        msgs = assert_message_and_return_remaining(
            msgs,
            lambda msg: msg.command == "read"
            and msg.obj.name == "grid_scan_device-expected_images",
        )

        msgs = assert_message_and_return_remaining(
            msgs,
            lambda msg: msg.command == "read"
            and msg.obj.name == "eiger_cam_acquire_time",
        )

        mock_check_topup.assert_called_once()
        mock_read_hardware.assert_called_once()

        msgs = assert_message_and_return_remaining(
            msgs, lambda msg: msg.command == "wait"
        )

        msgs = assert_message_and_return_remaining(
            msgs,
            lambda msg: msg.command == "kickoff" and msg.obj.name == "grid_scan_device",
        )

        msgs = assert_message_and_return_remaining(
            msgs, lambda msg: msg.command == "wait"
        )

        msgs = assert_message_and_return_remaining(
            msgs, lambda msg: msg.command == "null"
        )

        msgs = assert_message_and_return_remaining(
            msgs,
            lambda msg: msg.command == "complete"
            and msg.obj.name == "grid_scan_device",
        )

        msgs = assert_message_and_return_remaining(
            msgs, lambda msg: msg.command == "wait"
        )


def test_do_fgs_optionally_calls_during_collection_plan(
    sim_run_engine: RunEngineSimulator, fgs_devices
):
    with patch("mx_bluesky.common.plan_stubs.do_fgs.check_topup_and_wait_if_necessary"):
        synchrotron = fgs_devices["synchrotron"]
        detector = fgs_devices["detector"]
        fgs_device = fgs_devices["grid_scan_device"]
        msgs = sim_run_engine.simulate_plan(
            do_fgs(
                fgs_device,
                detector,
                synchrotron,
            )
        )
        null_messages = [msg for msg in msgs if msg.command == "null"]
        assert len(null_messages) == 0


def test_do_fgs_with_run_engine(RE: RunEngine, fgs_devices):
    synchrotron = fgs_devices["synchrotron"]
    set_mock_value(synchrotron.synchrotron_mode, SynchrotronMode.DEV)
    detector = fgs_devices["detector"]
    fgs_device: ZebraFastGridScan = fgs_devices["grid_scan_device"]

    def do_fgs_plan_in_run():
        yield from bps.open_run()
        yield from do_fgs(fgs_device, detector, synchrotron)
        yield from bps.close_run()

    set_mock_value(fgs_device.status, 1)

    with patch("mx_bluesky.common.plan_stubs.do_fgs.bps.complete"):
        RE(do_fgs_plan_in_run())