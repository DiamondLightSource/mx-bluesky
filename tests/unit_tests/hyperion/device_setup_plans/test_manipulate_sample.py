from unittest.mock import MagicMock, Mock

from bluesky import Msg
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from dodal.devices.aperturescatterguard import ApertureValue
from dodal.devices.backlight import Backlight
from dodal.devices.smargon import CombinedMove, Smargon
from dodal.devices.thawer import Thawer

from mx_bluesky.common.device_setup_plans.beamsize.beamsize import BeamSizePlans
from mx_bluesky.common.device_setup_plans.manipulate_sample import (
    move_phi_chi,
    move_x_y_z,
    setup_sample_environment,
)
from mx_bluesky.common.parameters.constants import PlanGroupCheckpointConstants


def test_setup_sample_environment_waits_for_beamsize_prepare_then_performs(
    backlight: Backlight,
    thawer: Thawer,
    sim_run_engine: RunEngineSimulator,
):
    beamsize_devices = MagicMock()
    beamsize_device_plans = Mock(spec=BeamSizePlans)
    beamsize_device_plans.perform_beam_size.return_value = iter(
        [Msg("perform_beam_size")]
    )
    msgs = sim_run_engine.simulate_plan(
        setup_sample_environment(
            beamsize_devices,
            beamsize_device_plans,
            ApertureValue.MEDIUM,
            backlight,
            thawer,
        )
    )

    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: (
            msg.command == "wait"
            and msg.kwargs["group"] == PlanGroupCheckpointConstants.PREPARE_APERTURE
        ),
    )
    msgs = assert_message_and_return_remaining(
        msgs, lambda msg: msg.command == "perform_beam_size"
    )


def test_move_x_y_z_no_wait(
    smargon: Smargon,
    sim_run_engine: RunEngineSimulator,
):
    msgs = sim_run_engine.simulate_plan(move_x_y_z(smargon, 10.0, 5.0, None))
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: (
            msg.command == "set"
            and msg.obj.name == smargon.name
            and msg.args[0] == CombinedMove(x=10.0, y=5.0, z=None)
        ),
    )
    assert len(msgs) == 1


def test_move_x_y_z_wait(
    smargon: Smargon,
    sim_run_engine: RunEngineSimulator,
):
    msgs = sim_run_engine.simulate_plan(move_x_y_z(smargon, 10.0, 5.0, None, wait=True))
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: (
            msg.command == "set"
            and msg.obj.name == smargon.name
            and msg.args[0] == CombinedMove(x=10.0, y=5.0, z=None)
        ),
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
    msgs = sim_run_engine.simulate_plan(move_phi_chi(smargon, 10.0, 5.0))
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: (
            msg.command == "set"
            and msg.obj.name == smargon.name
            and msg.args[0] == CombinedMove(phi=10.0, chi=5.0)
        ),
    )
    assert len(msgs) == 1


def test_move_phi_chi_omega_wait(
    smargon: Smargon,
    sim_run_engine: RunEngineSimulator,
):
    msgs = sim_run_engine.simulate_plan(move_phi_chi(smargon, 10.0, 5.0, wait=True))
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: (
            msg.command == "set"
            and msg.obj.name == smargon.name
            and msg.args[0] == CombinedMove(phi=10.0, chi=5.0)
        ),
    )
    group = msgs[0].kwargs["group"]
    assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "wait" and msg.kwargs["group"] == group,
    )
