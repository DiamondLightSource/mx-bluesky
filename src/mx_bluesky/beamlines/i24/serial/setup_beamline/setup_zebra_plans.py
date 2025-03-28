"""
Zebra setup plans for extruder and fastchip serial collections.

For clarification on the Zebra setup in either use case, please see
https://confluence.diamond.ac.uk/display/MXTech/Zebra+settings+I24

Note on soft inputs. In the code, soft inputs are 1 indexed following the numbering on
the edm screen, while on the schematics they are 0 indexed. Thus, `Soft In 1` from the
schematics corresponds to soft_in_2 in the code.
"""

import bluesky.plan_stubs as bps
from dodal.devices.zebra.zebra import (
    ArmDemand,
    ArmSource,
    I24Axes,
    RotationDirection,
    SoftInState,
    TrigSource,
    Zebra,
)

from mx_bluesky.beamlines.i24.serial.log import SSX_LOGGER

# Detector specific outs
TTL_EIGER = 1
TTL_PILATUS = 2
TTL_FAST_SHUTTER = 4

SHUTTER_MODE = {
    "manual": SoftInState.NO,
    "auto": SoftInState.YES,
}

GATE_START = 1.0
SHUTTER_OPEN_TIME = 0.05  # For pp with long delays


def get_zebra_settings_for_extruder(
    exp_time: float,
    pump_exp: float,
    pump_delay: float,
) -> tuple[float, float]:
    """Calculates and returns gate width and step for extruder collections with pump \
    probe.

    The gate width is calculated by adding the exposure time, pump exposure and \
    pump delay. From this value, the gate step is obtained by adding a 0.01 buffer to \
    the width. The value of this buffer is empirically determined.
    """
    pump_probe_buffer = 0.01
    gate_width = pump_exp + pump_delay + exp_time
    gate_step = gate_width + pump_probe_buffer
    return gate_width, gate_step


def arm_zebra(zebra: Zebra):
    yield from bps.abs_set(zebra.pc.arm, ArmDemand.ARM, wait=True)
    SSX_LOGGER.info("Zebra armed.")


def disarm_zebra(zebra: Zebra):
    yield from bps.abs_set(zebra.pc.arm, ArmDemand.DISARM, wait=True)
    SSX_LOGGER.info("Zebra disarmed.")


def open_fast_shutter(zebra: Zebra):
    yield from bps.abs_set(zebra.inputs.soft_in_2, SoftInState.YES, wait=True)
    SSX_LOGGER.info("Fast shutter open.")


def close_fast_shutter(zebra: Zebra):
    yield from bps.abs_set(zebra.inputs.soft_in_2, SoftInState.NO, wait=True)
    SSX_LOGGER.info("Fast shutter closed.")


def set_shutter_mode(zebra: Zebra, mode: str):
    # SOFT_IN:B0 has to be disabled for manual mode
    yield from bps.abs_set(zebra.inputs.soft_in_1, SHUTTER_MODE[mode], wait=True)
    SSX_LOGGER.info(f"Shutter mode set to {mode}.")


def setup_pc_sources(
    zebra: Zebra,
    gate_source: TrigSource,
    pulse_source: TrigSource,
    group: str = "pc_sources",
):
    yield from bps.abs_set(zebra.pc.gate_source, gate_source, group=group)
    yield from bps.abs_set(zebra.pc.pulse_source, pulse_source, group=group)
    yield from bps.wait(group)


def setup_zebra_for_quickshot_plan(
    zebra: Zebra,
    exp_time: float,
    num_images: int,
    group: str = "setup_zebra_for_quickshot",
    wait: bool = True,
):
    """Set up the zebra for a static extruder experiment.

    Gate source set to 'External' and Pulse source set to 'Time'.
    The gate start is set to 1.0 and the gate width is calculated from \
    exposure time*number of images plus a 0.5 buffer.

    Args:
        zebra (Zebra): The zebra ophyd device.
        exp_time (float): Collection exposure time, in s.
        num_images (float): Number of images to be collected.
    """
    SSX_LOGGER.info("Setup ZEBRA for quickshot collection.")
    yield from bps.abs_set(zebra.pc.arm_source, ArmSource.SOFT, group=group)
    yield from setup_pc_sources(zebra, TrigSource.TIME, TrigSource.EXTERNAL)

    gate_width = exp_time * num_images + 0.5
    SSX_LOGGER.info(f"Gate start set to {GATE_START}, with width {gate_width}.")
    yield from bps.abs_set(zebra.pc.gate_start, GATE_START, group=group)
    yield from bps.abs_set(zebra.pc.gate_width, gate_width, group=group)

    yield from bps.abs_set(
        zebra.pc.gate_input, zebra.mapping.sources.SOFT_IN2, group=group
    )
    yield from bps.sleep(0.1)

    if wait:
        yield from bps.wait(group)
    SSX_LOGGER.info("Finished setting up zebra.")


def set_logic_gates_for_porto_triggering(
    zebra: Zebra, group: str = "porto_logic_gates"
):
    # To OUT2_TTL
    yield from bps.abs_set(
        zebra.logic_gates.and_gates[3].sources[1],
        zebra.mapping.sources.SOFT_IN2,
        group=group,
    )
    yield from bps.abs_set(
        zebra.logic_gates.and_gates[3].sources[2],
        zebra.mapping.sources.PULSE1,
        group=group,
    )
    # To OUT1_TTL
    yield from bps.abs_set(
        zebra.logic_gates.and_gates[4].sources[1],
        zebra.mapping.sources.SOFT_IN2,
        group=group,
    )
    yield from bps.abs_set(
        zebra.logic_gates.and_gates[4].sources[2],
        zebra.mapping.sources.PULSE2,
        group=group,
    )
    yield from bps.wait(group=group)


def setup_zebra_for_extruder_with_pump_probe_plan(
    zebra: Zebra,
    det_type: str,
    exp_time: float,
    num_images: int,
    pump_exp: float | None,
    pump_delay: float | None,
    pulse1_delay: float = 0.0,
    group: str = "setup_zebra_for_extruder_pp",
    wait: bool = True,
):
    """Zebra setup for extruder pump probe experiment using PORTO laser triggering.

    For this use case, both the laser and detector set up is taken care of by the Zebra.
    WARNING. This means that some hardware changes have been made.
    Because all four of the zebra ttl outputs are in use in this mode, when the \
    detector in use is the Eiger, the Pilatus cable is repurposed to trigger the light \
    source, and viceversa.

    The data collection output is OUT1_TTL for Eiger and OUT2_TTL for Pilatus and \
    should be set to AND3.

    Position compare settings:
        - The gate input is on SOFT_IN2.
        - The number of gates should be equal to the number of images to collect.
        - Gate source set to 'Time' and Pulse source set to 'External'.

    Pulse output settings:
        - Pulse1 is the laser control on the Zebra. It is set with a 0.0 delay and a \
            width equal to the requested laser dwell.
        - Pulse2 is the detector control. It is set with a delay equal to the laser \
            delay and a width equal to the exposure time.

    Args:
        zebra (Zebra): The zebra ophyd device.
        det_type (str): Detector in use, current choices are Eiger or Pilatus.
        exp_time (float): Collection exposure time, in s.
        num_images (int): Number of images to be collected.
        pump_exp (float): Laser dwell, in s.
        pump_delay (float): Laser delay, in s.
        pulse1_delay (float, optional): Delay to start pulse1 (the laser control) after \
            gate start. Defaults to 0.0.
    """
    SSX_LOGGER.info("Setup ZEBRA for pump probe extruder collection.")

    yield from set_shutter_mode(zebra, "manual")

    # Set gate to "Time" and pulse source to "External"
    yield from setup_pc_sources(zebra, TrigSource.TIME, TrigSource.EXTERNAL)

    # Logic gates
    yield from set_logic_gates_for_porto_triggering(zebra)

    # Set TTL out depending on detector type
    DET_TTL = TTL_EIGER if det_type == "eiger" else TTL_PILATUS
    LASER_TTL = TTL_PILATUS if det_type == "eiger" else TTL_EIGER
    yield from bps.abs_set(
        zebra.output.out_pvs[DET_TTL], zebra.mapping.sources.AND4, group=group
    )
    yield from bps.abs_set(
        zebra.output.out_pvs[LASER_TTL], zebra.mapping.sources.AND3, group=group
    )

    yield from bps.abs_set(
        zebra.pc.gate_input, zebra.mapping.sources.SOFT_IN2, group=group
    )

    assert pump_exp and pump_delay, "Must supply pump_exp and pump_delay!"
    gate_width, gate_step = get_zebra_settings_for_extruder(
        exp_time, pump_exp, pump_delay
    )
    SSX_LOGGER.info(
        f"""
        Gate start set to {GATE_START}, with calculated width {gate_width}
        and step {gate_step}.
        """
    )
    yield from bps.abs_set(zebra.pc.gate_start, GATE_START, group=group)
    yield from bps.abs_set(zebra.pc.gate_width, gate_width, group=group)
    yield from bps.abs_set(zebra.pc.gate_step, gate_step, group=group)
    # Number of gates is the same as the number of images
    yield from bps.abs_set(zebra.pc.num_gates, num_images, group=group)

    # Settings for extruder pump probe:
    # PULSE1_DLY is the start (0 usually), PULSE1_WID is the laser dwell set on edm
    # PULSE2_DLY is the laser delay set on edm, PULSE2_WID is the exposure time
    SSX_LOGGER.info(
        f"Pulse1 starting at {pulse1_delay} with width set to laser dwell {pump_exp}."
    )
    yield from bps.abs_set(
        zebra.output.pulse_1.input, zebra.mapping.sources.PC_GATE, group=group
    )
    yield from bps.abs_set(zebra.output.pulse_1.delay, pulse1_delay, group=group)
    yield from bps.abs_set(zebra.output.pulse_1.width, pump_exp, group=group)
    SSX_LOGGER.info(
        f"""
        Pulse2 starting at laser delay {pump_delay} with width set to \
        exposure time {exp_time}.
        """
    )
    yield from bps.abs_set(
        zebra.output.pulse_2.input, zebra.mapping.sources.PC_GATE, group=group
    )
    yield from bps.abs_set(zebra.output.pulse_2.delay, pump_delay, group=group)
    yield from bps.abs_set(zebra.output.pulse_2.width, exp_time, group=group)

    if wait:
        yield from bps.wait(group)
    SSX_LOGGER.info("Finished setting up zebra.")


def setup_zebra_for_fastchip_plan(
    zebra: Zebra,
    det_type: str,
    num_gates: int,
    num_exposures: int,
    exposure_time_s: float,
    start_time_offset: float = 0.0,
    group: str = "setup_zebra_for_fastchip",
    wait: bool = True,
):
    """Zebra setup for fixed-target triggering.

    For this use case, the laser set up is taken care of by the geobrick, leaving only \
    the detector side set up to the Zebra.
    The data collection output is OUT1_TTL for Eiger and OUT2_TTL for Pilatus and \
    should be set to AND3.

    Position compare settings:
        - The gate input is on IN3_TTL.
        - The number of gates should be equal to the number of apertures to collect.
        - Gate source set to 'External' and Pulse source set to 'Time'
        - Trigger source set to the exposure time with a 100us buffer in order to \
            avoid missing any triggers.
        - The trigger width is calculated depending on which detector is in use: the \
            Pilatus only needs the trigger rising edge to collect for a set time, while \
            the Eiger (used here in Externally Interrupter Exposure Series mode) \
            will only collect while the signal is high and will stop once a falling \
            edge is detected. For this reason a square wave pulse width will be set to \
            half the exposure time in the Pilatus case, and to the exposure time minus \
            a small drop (~100um) for the Eiger.

    Args:
        zebra (Zebra): The zebra ophyd device.
        det_type (str): Detector in use, current choices are Eiger or Pilatus.
        num_gates (int): Number of apertures to visit in a chip.
        num_exposures (int): Number of times data is collected in each aperture.
        exposure_time_s (float): Exposure time for each shot.
        start_time_offset (float): Delay on the start of the position compare. \
            Defaults to 0.0 (standard chip collection).
    """
    SSX_LOGGER.info("Setup ZEBRA for a fixed target collection.")

    yield from set_shutter_mode(zebra, "manual")

    yield from setup_pc_sources(zebra, TrigSource.EXTERNAL, TrigSource.TIME)

    # Logic Gates
    yield from bps.abs_set(
        zebra.logic_gates.and_gates[3].sources[1],
        zebra.mapping.sources.SOFT_IN2,
        group=group,
    )
    yield from bps.abs_set(
        zebra.logic_gates.and_gates[3].sources[2],
        zebra.mapping.sources.PC_PULSE,
        group=group,
    )

    yield from bps.abs_set(
        zebra.pc.gate_input, zebra.mapping.sources.IN3_TTL, group=group
    )

    # Set TTL out depending on detector type
    # And calculate some of the other settings
    if det_type == "eiger":
        yield from bps.abs_set(
            zebra.output.out_pvs[TTL_EIGER], zebra.mapping.sources.AND3, group=group
        )
    if det_type == "pilatus":
        yield from bps.abs_set(
            zebra.output.out_pvs[TTL_PILATUS], zebra.mapping.sources.AND3, group=group
        )

    # Square wave - needs a small drop to make it work for eiger
    pulse_width = (
        exposure_time_s - 0.0001 if det_type == "eiger" else exposure_time_s / 2
    )

    # 100us buffer needed to avoid missing some of the triggers
    exptime_buffer = exposure_time_s + 0.0001

    # Number of gates is the number of windows collected
    yield from bps.abs_set(zebra.pc.num_gates, num_gates, group=group)

    yield from bps.abs_set(zebra.pc.pulse_start, start_time_offset, group=group)
    yield from bps.abs_set(zebra.pc.pulse_step, exptime_buffer, group=group)
    yield from bps.abs_set(zebra.pc.pulse_width, pulse_width, group=group)
    yield from bps.abs_set(zebra.pc.pulse_max, num_exposures, group=group)

    if wait:
        yield from bps.wait(group)
    SSX_LOGGER.info("Finished setting up zebra.")


def open_fast_shutter_at_each_position_plan(
    zebra: Zebra,
    num_exposures: int,
    exposure_time_s: float,
    group: str = "fast_shutter_control",
    wait: bool = True,
):
    """A plan to control the fast shutter so that it will open at each position.
    This plan is a specific setup for pump probe fixed target triggering with long \
    delays between exposures.

    For this use case, the fast shutter opens and closes at every position to avoid \
    destroying the crystals by exposing them to the beam for a long time in between \
    collections.

    The shutter opening time, hardcoded to 0.05, has been empirically determined.

    Fast shutter (Pulse2) output settings:
        - Output is OUT4_TTL set to PULSE2.
        - Pulse2 is set with a delay equal to 0 and a width equal to the exposure time \
            multiplied by the number of exposures, plus the shutter opening time.

    Args:
        zebra (Zebra): The zebra ophyd device.
        num_exposures (int): Number of times data is collected in each aperture.
        exposure_time_s (float): Exposure time for each shot.
    """
    SSX_LOGGER.info(
        "ZEBRA setup for fastchip collection with long delays between exposures."
    )
    SSX_LOGGER.debug("Controlling the fast shutter on PULSE2.")
    # Output panel pulse_2 settings
    yield from bps.abs_set(
        zebra.output.pulse_2.input, zebra.mapping.sources.PC_GATE, group=group
    )
    yield from bps.abs_set(zebra.output.pulse_2.delay, 0.0, group=group)
    pulse2_width = num_exposures * exposure_time_s + SHUTTER_OPEN_TIME
    yield from bps.abs_set(zebra.output.pulse_2.width, pulse2_width, group=group)

    # Fast shutter
    yield from bps.abs_set(
        zebra.output.out_pvs[TTL_FAST_SHUTTER],
        zebra.mapping.sources.PULSE2,
        group=group,
    )

    if wait:
        yield from bps.wait(group=group)
    SSX_LOGGER.debug("Finished setting up for long delays.")


def reset_pc_gate_and_pulse(zebra: Zebra, group: str = "reset_pc"):
    yield from bps.abs_set(zebra.pc.gate_start, 0, group=group)
    yield from bps.abs_set(zebra.pc.pulse_width, 0, group=group)
    yield from bps.abs_set(zebra.pc.pulse_step, 0, group=group)
    yield from bps.wait(group=group)


def reset_output_panel(zebra: Zebra, group: str = "reset_zebra_outputs"):
    # Reset TTL out
    yield from bps.abs_set(
        zebra.output.out_pvs[2], zebra.mapping.sources.PC_GATE, group=group
    )
    yield from bps.abs_set(
        zebra.output.out_pvs[3], zebra.mapping.sources.DISCONNECT, group=group
    )
    yield from bps.abs_set(
        zebra.output.out_pvs[4], zebra.mapping.sources.OR1, group=group
    )

    yield from bps.abs_set(
        zebra.output.pulse_1.input, zebra.mapping.sources.DISCONNECT, group=group
    )
    yield from bps.abs_set(
        zebra.output.pulse_2.input, zebra.mapping.sources.DISCONNECT, group=group
    )

    yield from bps.wait(group=group)


def zebra_return_to_normal_plan(
    zebra: Zebra, group: str = "zebra-return-to-normal", wait: bool = True
):
    """A plan to reset the Zebra settings at the end of a collection.

    This plan should only be run after disarming the Zebra.
    """
    yield from bps.abs_set(zebra.pc.reset, 1, group=group)

    # Reset PC_GATE and PC_SOURCE to "Position"
    yield from setup_pc_sources(zebra, TrigSource.POSITION, TrigSource.POSITION)

    yield from bps.abs_set(
        zebra.pc.gate_input, zebra.mapping.sources.SOFT_IN3, group=group
    )
    yield from bps.abs_set(zebra.pc.num_gates, 1, group=group)
    yield from bps.abs_set(
        zebra.pc.pulse_input, zebra.mapping.sources.DISCONNECT, group=group
    )

    # Logic Gates
    yield from bps.abs_set(
        zebra.logic_gates.and_gates[3].sources[1],
        zebra.mapping.sources.PC_ARM,
        group=group,
    )
    yield from bps.abs_set(
        zebra.logic_gates.and_gates[3].sources[2],
        zebra.mapping.sources.IN1_TTL,
        group=group,
    )

    # Reset TTL out
    yield from reset_output_panel(zebra)

    # Reset Pos Trigger and direction to rotation axis ("omega") and positive
    yield from bps.abs_set(zebra.pc.gate_trigger, I24Axes.OMEGA.value, group=group)
    yield from bps.abs_set(zebra.pc.dir, RotationDirection.POSITIVE, group=group)

    #
    yield from reset_pc_gate_and_pulse(zebra)

    if wait:
        yield from bps.wait(group)
    SSX_LOGGER.info("Zebra settings back to normal.")


def reset_zebra_when_collection_done_plan(zebra: Zebra):
    """
    End of collection zebra operations: close fast shutter, disarm and reset settings.
    """
    SSX_LOGGER.debug("Close the fast shutter.")
    yield from close_fast_shutter(zebra)
    SSX_LOGGER.debug("Disarm the zebra.")
    yield from disarm_zebra(zebra)
    SSX_LOGGER.debug("Set zebra back to normal.")
    yield from zebra_return_to_normal_plan(zebra, wait=True)
