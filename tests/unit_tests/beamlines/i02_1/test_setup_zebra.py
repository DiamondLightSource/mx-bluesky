import pytest
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from dodal.beamlines import i02_1
from dodal.devices.zebra.zebra import Zebra

from mx_bluesky.beamlines.i02_1.device_setup_plans.setup_zebra import (
    setup_zebra_for_gridscan,
    tidy_up_zebra_after_gridscan,
)
from mx_bluesky.common.parameters.constants import PlanGroupCheckpointConstants


@pytest.fixture
def zebra():
    return i02_1.zebra.build(connect_immediately=True, mock=True)


async def test_zebra_set_up_for_gridscan(
    sim_run_engine: RunEngineSimulator,
    zebra: Zebra,
):
    msgs = sim_run_engine.simulate_plan(setup_zebra_for_gridscan(zebra))
    assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == f"zebra-output-out_pvs-{zebra.mapping.outputs.TTL_EIGER}"
        and msg.args[0] == zebra.mapping.sources.IN1_TTL,
    )
    assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "wait"
        and msg.kwargs["group"]
        == PlanGroupCheckpointConstants.SETUP_ZEBRA_FOR_GRIDSCAN,
    )


async def test_tidy_up_zebra_after_gridscan(
    sim_run_engine: RunEngineSimulator,
    zebra: Zebra,
):
    msgs = sim_run_engine.simulate_plan(tidy_up_zebra_after_gridscan(zebra, wait=True))
    assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == f"zebra-output-out_pvs-{zebra.mapping.outputs.TTL_EIGER}"
        and msg.args[0] == zebra.mapping.sources.OR1,
    )
    assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "wait"
        and msg.kwargs["group"]
        == PlanGroupCheckpointConstants.TIDY_ZEBRA_AFTER_GRIDSCAN,
    )
