from unittest.mock import patch

import pytest
from bluesky.simulators import assert_message_and_return_remaining
from bluesky.utils import Msg
from dodal.devices.xbpm_feedback import Pause

from mx_bluesky.hyperion.experiment_plans.set_energy_plan import (
    SetEnergyComposite,
    set_energy_plan,
)


@pytest.fixture()
def set_energy_composite(
    attenuator, dcm, undulator_dcm, vfm, mirror_voltages, xbpm_feedback
):
    composite = SetEnergyComposite(
        vfm,
        mirror_voltages,
        dcm,
        undulator_dcm,
        xbpm_feedback,
        attenuator,
    )
    return composite


@patch(
    "mx_bluesky.hyperion.experiment_plans.set_energy_plan.dcm_pitch_roll_mirror_adjuster.adjust_dcm_pitch_roll_vfm_from_lut",
    return_value=iter([Msg("adjust_dcm_pitch_roll_vfm_from_lut")]),
)
def test_set_energy(
    mock_dcm_pra,
    sim_run_engine,
    set_energy_composite,
):
    messages = sim_run_engine.simulate_plan(
        set_energy_plan(11100, set_energy_composite)
    )
    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "set"
        and msg.obj.name == "xbpm_feedback-pause_feedback"
        and msg.args == (Pause.PAUSE,),
    )
    messages = assert_message_and_return_remaining(
        messages[1:],
        lambda msg: msg.command == "set"
        and msg.obj.name == "attenuator"
        and msg.args == (0.1,),
    )
    messages = assert_message_and_return_remaining(
        messages[1:],
        lambda msg: msg.command == "set"
        and msg.obj.name == "undulator_dcm"
        and msg.args == (11.1,)
        and msg.kwargs["group"] == "UNDULATOR_GROUP",
    )
    messages = assert_message_and_return_remaining(
        messages[1:], lambda msg: msg.command == "adjust_dcm_pitch_roll_vfm_from_lut"
    )
    messages = assert_message_and_return_remaining(
        messages[1:],
        lambda msg: msg.command == "wait" and msg.kwargs["group"] == "UNDULATOR_GROUP",
    )
    messages = assert_message_and_return_remaining(
        messages[1:],
        lambda msg: msg.command == "set"
        and msg.obj.name == "xbpm_feedback-pause_feedback"
        and msg.args == (Pause.RUN,),
    )
    messages = assert_message_and_return_remaining(
        messages[1:],
        lambda msg: msg.command == "set"
        and msg.obj.name == "attenuator"
        and msg.args == (1.0,),
    )


@patch(
    "mx_bluesky.hyperion.experiment_plans.set_energy_plan.dcm_pitch_roll_mirror_adjuster.adjust_dcm_pitch_roll_vfm_from_lut",
    return_value=iter([Msg("adjust_dcm_pitch_roll_vfm_from_lut")]),
)
def test_set_energy_does_nothing_if_no_energy_specified(
    mock_dcm_pra,
    sim_run_engine,
    set_energy_composite,
):
    messages = sim_run_engine.simulate_plan(set_energy_plan(None, set_energy_composite))
    assert not messages
