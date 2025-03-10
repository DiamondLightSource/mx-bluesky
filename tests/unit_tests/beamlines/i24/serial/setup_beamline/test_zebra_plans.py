import pytest
from dodal.devices.zebra.zebra import (
    TrigSource,
    Zebra,
)

from mx_bluesky.beamlines.i24.serial.setup_beamline.setup_zebra_plans import (
    arm_zebra,
    disarm_zebra,
    get_zebra_settings_for_extruder,
    open_fast_shutter_at_each_position_plan,
    reset_output_panel,
    reset_pc_gate_and_pulse,
    reset_zebra_when_collection_done_plan,
    set_shutter_mode,
    setup_pc_sources,
    setup_zebra_for_extruder_with_pump_probe_plan,
    setup_zebra_for_fastchip_plan,
    setup_zebra_for_quickshot_plan,
    zebra_return_to_normal_plan,
)


async def test_arm_and_disarm_zebra(zebra: Zebra, RE):
    zebra.pc.arm.TIMEOUT = 1

    RE(arm_zebra(zebra))
    assert await zebra.pc.is_armed()

    RE(disarm_zebra(zebra))
    assert await zebra.pc.is_armed() is False


async def test_set_shutter_mode(zebra: Zebra, RE):
    RE(set_shutter_mode(zebra, "manual"))
    assert await zebra.inputs.soft_in_1.get_value() == "No"


async def test_setup_pc_sources(zebra: Zebra, RE):
    RE(setup_pc_sources(zebra, TrigSource.TIME, TrigSource.POSITION))

    assert await zebra.pc.gate_source.get_value() == "Time"
    assert await zebra.pc.pulse_source.get_value() == "Position"


def test_get_zebra_settings_for_extruder_pumpprobe():
    width, step = get_zebra_settings_for_extruder(0.01, 0.005, 0.001)
    assert round(width, 3) == 0.016
    assert round(step, 3) == 0.026


async def test_setup_zebra_for_quickshot(zebra: Zebra, RE):
    RE(setup_zebra_for_quickshot_plan(zebra, exp_time=0.001, num_images=10, wait=True))
    assert await zebra.pc.arm_source.get_value() == "Soft"
    assert await zebra.pc.gate_start.get_value() == 1.0
    assert await zebra.pc.gate_input.get_value() == zebra.mapping.sources.SOFT_IN2


async def test_setup_zebra_for_extruder_pp_eiger_collection(zebra: Zebra, RE):
    inputs_list = (0.01, 10, 0.005, 0.001)
    # With eiger
    RE(
        setup_zebra_for_extruder_with_pump_probe_plan(
            zebra, "eiger", *inputs_list, wait=True
        )
    )
    assert await zebra.output.out_pvs[1].get_value() == zebra.mapping.sources.AND4
    assert await zebra.output.out_pvs[2].get_value() == zebra.mapping.sources.AND3

    assert await zebra.inputs.soft_in_1.get_value() == "No"
    assert (
        await zebra.logic_gates.and_gates[3].sources[1].get_value()
        == zebra.mapping.sources.SOFT_IN2
    )
    assert await zebra.pc.num_gates.get_value() == 10


async def test_setup_zebra_for_extruder_pp_pilatus_collection(zebra: Zebra, RE):
    inputs_list = (0.01, 10, 0.005, 0.001)
    # With pilatus
    RE(
        setup_zebra_for_extruder_with_pump_probe_plan(
            zebra, "pilatus", *inputs_list, wait=True
        )
    )
    # Check that SOFT_IN:B0 gets disabled
    assert await zebra.output.out_pvs[1].get_value() == zebra.mapping.sources.AND3

    assert await zebra.pc.gate_start.get_value() == 1.0
    assert await zebra.output.pulse_1.delay.get_value() == 0.0
    assert await zebra.output.pulse_2.delay.get_value() == 0.001


async def test_setup_zebra_for_fastchip(zebra: Zebra, RE):
    num_gates = 400
    num_exposures = 2
    exposure_time_s = 0.001
    # With Eiger
    RE(
        setup_zebra_for_fastchip_plan(
            zebra, "eiger", num_gates, num_exposures, exposure_time_s, wait=True
        )
    )
    # Check that SOFT_IN:B0 gets disabled
    assert await zebra.output.out_pvs[1].get_value() == zebra.mapping.sources.AND3

    # Check ttl out1 is set to AND3
    assert await zebra.output.out_pvs[1].get_value() == zebra.mapping.sources.AND3
    assert await zebra.pc.num_gates.get_value() == num_gates
    assert await zebra.pc.pulse_max.get_value() == num_exposures
    assert await zebra.pc.pulse_width.get_value() == exposure_time_s - 0.0001

    # With Pilatus
    RE(
        setup_zebra_for_fastchip_plan(
            zebra, "pilatus", num_gates, num_exposures, exposure_time_s, wait=True
        )
    )
    # Check ttl out2 is set to AND3
    assert await zebra.output.out_pvs[2].get_value() == zebra.mapping.sources.AND3

    assert await zebra.pc.pulse_start.get_value() == 0.0
    assert await zebra.pc.pulse_width.get_value() == exposure_time_s / 2
    assert await zebra.pc.pulse_step.get_value() == exposure_time_s + 0.0001


async def test_open_fast_shutter_at_each_position_plan(zebra: Zebra, RE):
    num_exposures = 2
    exposure_time_s = 0.001

    RE(open_fast_shutter_at_each_position_plan(zebra, num_exposures, exposure_time_s))

    # Check output Pulse2 is set
    assert await zebra.output.pulse_2.input.get_value() == zebra.mapping.sources.PC_GATE
    assert await zebra.output.pulse_2.delay.get_value() == 0.0
    expected_pulse_width = num_exposures * exposure_time_s + 0.05
    assert await zebra.output.pulse_2.width.get_value() == pytest.approx(
        expected_pulse_width, abs=1e-3
    )

    assert await zebra.output.out_pvs[4].get_value() == zebra.mapping.sources.PULSE2


async def test_reset_pc_gate_and_pulse(zebra: Zebra, RE):
    RE(reset_pc_gate_and_pulse(zebra))

    assert await zebra.pc.gate_start.get_value() == 0
    assert await zebra.pc.pulse_width.get_value() == 0
    assert await zebra.pc.pulse_step.get_value() == 0


async def test_reset_output_panel(zebra: Zebra, RE):
    RE(reset_output_panel(zebra))

    assert await zebra.output.out_pvs[2].get_value() == zebra.mapping.sources.PC_GATE
    assert await zebra.output.out_pvs[4].get_value() == zebra.mapping.sources.OR1
    assert (
        await zebra.output.pulse_1.input.get_value() == zebra.mapping.sources.DISCONNECT
    )
    assert (
        await zebra.output.pulse_2.input.get_value() == zebra.mapping.sources.DISCONNECT
    )


async def test_zebra_return_to_normal(zebra: Zebra, RE):
    RE(zebra_return_to_normal_plan(zebra, wait=True))

    assert await zebra.pc.reset.get_value() == 1
    assert await zebra.pc.gate_source.get_value() == "Position"
    assert await zebra.pc.pulse_source.get_value() == "Position"
    assert await zebra.pc.gate_trigger.get_value() == "Enc2"
    assert await zebra.pc.gate_start.get_value() == 0

    assert await zebra.output.out_pvs[3].get_value() == zebra.mapping.sources.DISCONNECT
    assert (
        await zebra.output.pulse_1.input.get_value() == zebra.mapping.sources.DISCONNECT
    )


async def test_reset_zebra_plan(zebra: Zebra, RE):
    RE(reset_zebra_when_collection_done_plan(zebra))

    assert await zebra.inputs.soft_in_2.get_value() == "No"
    assert await zebra.pc.is_armed() is False
