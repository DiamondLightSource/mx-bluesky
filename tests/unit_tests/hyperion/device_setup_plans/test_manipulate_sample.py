import pytest
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from dodal.devices.aperturescatterguard import ApertureScatterguard, ApertureValue
from dodal.devices.smargon import CombinedMove, Smargon
from ophyd_async.testing import get_mock_put

from mx_bluesky.common.device_setup_plans.manipulate_sample import (
    move_aperture_if_required,
    move_phi_chi_omega,
    move_x_y_z,
)


@pytest.mark.parametrize(
    "set_position",
    [
        (ApertureValue.SMALL),
        (ApertureValue.MEDIUM),
        (ApertureValue.OUT_OF_BEAM),
        (ApertureValue.LARGE),
    ],
)
async def test_move_aperture_goes_to_correct_position(
    aperture_scatterguard: ApertureScatterguard,
    run_engine: RunEngine,
    set_position,
):
    run_engine(move_aperture_if_required(aperture_scatterguard, set_position))
    last_pos = get_mock_put(aperture_scatterguard.selected_aperture).call_args[0]
    assert last_pos == (set_position,)


async def test_move_aperture_does_nothing_when_none_selected(
    aperture_scatterguard: ApertureScatterguard, run_engine: RunEngine
):
    get_mock_put(aperture_scatterguard.selected_aperture).reset_mock()
    run_engine(move_aperture_if_required(aperture_scatterguard, None))
    mock_put = get_mock_put(aperture_scatterguard.selected_aperture)
    mock_put.assert_not_called()


def test_move_x_y_z_no_wait(
    smargon: Smargon,
    sim_run_engine: RunEngineSimulator,
):
    msgs = sim_run_engine.simulate_plan(move_x_y_z(smargon, 10.0, 5.0, None))
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == smargon.name
        and msg.args[0] == CombinedMove(x=10.0, y=5.0, z=None),
    )
    assert len(msgs) == 1


def test_move_x_y_z_wait(
    smargon: Smargon,
    sim_run_engine: RunEngineSimulator,
):
    msgs = sim_run_engine.simulate_plan(move_x_y_z(smargon, 10.0, 5.0, None, wait=True))
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == smargon.name
        and msg.args[0] == CombinedMove(x=10.0, y=5.0, z=None),
    )
    group = msgs[0].kwargs["group"]
    assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "wait" and msg.kwargs["group"] == group,
    )


def test_move_phi_chi_omega_no_wait(
    smargon: Smargon,
    sim_run_engine: RunEngineSimulator,
):
    msgs = sim_run_engine.simulate_plan(move_phi_chi_omega(smargon, 10.0, 5.0, None))
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == smargon.name
        and msg.args[0] == CombinedMove(phi=10.0, chi=5.0, omega=None),
    )
    assert len(msgs) == 1


def test_move_phi_chi_omega_wait(
    smargon: Smargon,
    sim_run_engine: RunEngineSimulator,
):
    msgs = sim_run_engine.simulate_plan(
        move_phi_chi_omega(smargon, 10.0, 5.0, None, wait=True)
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == smargon.name
        and msg.args[0] == CombinedMove(phi=10.0, chi=5.0, omega=None),
    )
    group = msgs[0].kwargs["group"]
    assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "wait" and msg.kwargs["group"] == group,
    )
