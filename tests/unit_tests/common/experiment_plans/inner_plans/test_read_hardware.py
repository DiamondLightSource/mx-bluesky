from __future__ import annotations

import bluesky.plan_stubs as bps
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining

from mx_bluesky.common.device_setup_plans.detector.beamline_specific import (
    BeamlineSpecificDetectorFeatures,
)
from mx_bluesky.common.experiment_plans.inner_plans.read_hardware import (
    read_hardware_for_zocalo,
)


def test_read_hardware_for_zocalo_in_run_engine(
    beamline_specific_detector: BeamlineSpecificDetectorFeatures, run_engine: RunEngine
):
    def open_run_and_read_hardware():
        yield from bps.open_run()
        yield from read_hardware_for_zocalo(beamline_specific_detector)

    run_engine(open_run_and_read_hardware())


def test_read_hardware_correct_messages(
    beamline_specific_detector: BeamlineSpecificDetectorFeatures,
    sim_run_engine: RunEngineSimulator,
):
    msgs = sim_run_engine.simulate_plan(
        read_hardware_for_zocalo(beamline_specific_detector)
    )
    msgs = assert_message_and_return_remaining(
        msgs, lambda msg: msg.command == "create"
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: (
            msg.command == "read" and msg.obj.name == "eiger_odin_file_writer_id"
        ),
    )
    msgs = assert_message_and_return_remaining(msgs, lambda msg: msg.command == "save")
