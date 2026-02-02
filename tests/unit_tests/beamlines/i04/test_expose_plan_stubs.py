from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from dodal.devices.scintillator import InOut, Scintillator

from mx_bluesky.beamlines.i04.expose_plan_stubs import do_plan_stup


def test_do_plan_stub_on_scintillator_move_in(
    scintillator: Scintillator,
    sim_run_engine: RunEngineSimulator,
):
    msgs = sim_run_engine.simulate_plan(
        do_plan_stup("mv", "scintillator", "In", scintillator=scintillator)
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "scintillator"
        and msg.args[0] == InOut.IN,
    )


def test_do_plan_stub_on_scintillator_move_out(
    scintillator: Scintillator,
    sim_run_engine: RunEngineSimulator,
):
    msgs = sim_run_engine.simulate_plan(
        do_plan_stup("mv", "scintillator", "Out", scintillator=scintillator)
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "scintillator"
        and msg.args[0] == InOut.OUT,
    )
