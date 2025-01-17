import bluesky.plan_stubs as bps
from dodal.devices.zebra import (
    DISCONNECT,
    OR1,
    PC_PULSE,
    TTL_DETECTOR,
    TTL_XSPRESS3,
    EncEnum,
    I24Axes,
    RotationDirection,
    TrigSource,
    Zebra,
)

from mx_bluesky.beamlines.i24.jungfrau_commissioning.utils.log import LOGGER

TTL_SHUTTER = 4


def setup_zebra_for_rotation(
    zebra: Zebra,
    axis: EncEnum = I24Axes.OMEGA,
    start_angle: float = 0,
    scan_width: float = 360,
    direction: RotationDirection = RotationDirection.POSITIVE,
    shutter_opening_deg: float = 10,
    group: str = "setup_zebra_for_rotation",
    wait: bool = False,
    shutter_opening_s: float = 0.3,
):
    """Set up the Zebra to collect a rotation dataset. Any plan using this is
    responsible for setting the smargon velocity appropriately so that the desired
    image width is achieved with the exposure time given here.

    Parameters:
        axis:               I03 axes enum representing which axis to use for position
                            compare. Currently always omega.
        start_angle:        Position at which the scan should begin, in degrees.
        scan_width:         Total angle through which to collect, in degrees.
        direction:          RotationDirection enum for representing the direction of
                            rotation of the axis. Used for adjusting the start angle
                            based on shutter time.
        shutter_opening_deg How many degrees of movement to delay the pulse to
                            trigger the detector after the shutter opening signal
                            has been sent, and increase the gate width by to ensure
                            rotation through the full scan.
    """
    if not isinstance(direction, RotationDirection):
        raise ValueError(
            "Disallowed rotation direction provided to Zebra setup plan. "
            "Use RotationDirection.POSITIVE or RotationDirection.NEGATIVE."
        )

    LOGGER.info("ZEBRA SETUP: START")
    LOGGER.info("ZEBRA SETUP: Enable PC")
    yield from bps.abs_set(zebra.pc.gate_source, TrigSource.POSITION, group=group)
    yield from bps.abs_set(zebra.pc.pulse_source, TrigSource.TIME, group=group)
    # must be on for shutter trigger to be enabled
    yield from bps.abs_set(zebra.inputs.soft_in_1, 1, group=group)
    # set rotation direction
    yield from bps.abs_set(zebra.pc.dir, direction.value, group=group)
    # Set gate start, adjust for shutter opening time if necessary
    LOGGER.info(f"ZEBRA SETUP: shutter_opening_deg = {shutter_opening_deg}")
    LOGGER.info(f"ZEBRA SETUP: start angle start: {start_angle}")
    shutter_adjusted_start_angle = start_angle - (
        shutter_opening_deg * direction.multiplier
    )
    LOGGER.info(f"ZEBRA SETUP: {shutter_adjusted_start_angle=} for gate start")
    yield from bps.abs_set(
        zebra.pc.gate_start,
        shutter_adjusted_start_angle,
        group=group,
    )
    # adjust pulse start for shutter time
    yield from bps.abs_set(zebra.pc.pulse_start, shutter_opening_s, group=group)
    # set gate width to total width
    yield from bps.abs_set(
        zebra.pc.gate_width,
        scan_width + abs(shutter_opening_deg),
        group=group,
    )
    # Set gate position to be angle of interest
    yield from bps.abs_set(zebra.pc.gate_trigger, axis.value, group=group)
    # Set pulse width lower than exposure time
    yield from bps.abs_set(zebra.pc.pulse_width, 0.0005, group=group)
    # Trigger the shutter with the gate (from PC_GATE & SOFTIN1 -> OR1)
    yield from bps.abs_set(zebra.output.out_pvs[TTL_SHUTTER], OR1, group=group)
    # Trigger the detector with a pulse
    yield from bps.abs_set(zebra.output.out_pvs[TTL_DETECTOR], PC_PULSE, group=group)
    # Don't use the fluorescence detector
    yield from bps.abs_set(zebra.output.out_pvs[TTL_XSPRESS3], DISCONNECT, group=group)
    yield from bps.abs_set(zebra.output.pulse_1.input, DISCONNECT, group=group)
    LOGGER.info(f"ZEBRA SETUP: END - {'' if wait else 'not'} waiting for completion")
    if wait:
        yield from bps.wait(group)


def set_zebra_shutter_to_manual(
    zebra: Zebra, group="set_zebra_shutter_to_manual", wait=False
):
    yield from bps.abs_set(zebra.output.out_pvs[TTL_DETECTOR], PC_PULSE, group=group)
    yield from bps.abs_set(zebra.output.out_pvs[TTL_SHUTTER], OR1, group=group)

    if wait:
        yield from bps.wait(group)


def setup_zebra_for_darks(
    zebra: Zebra,
    axis: EncEnum = I24Axes.OMEGA,
    group: str = "setup_zebra_for_darks",
    wait: bool = False,
):
    """Set up the Zebra to collect a rotation dataset. Move omega from 0 to 1 to start
    the detector with a single pulse.
    """
    LOGGER.info("ZEBRA SETUP: START")
    LOGGER.info("ZEBRA SETUP: Enable PC")
    yield from bps.abs_set(zebra.pc.gate_source, TrigSource.POSITION, group=group)
    yield from bps.abs_set(zebra.pc.pulse_source, TrigSource.POSITION, group=group)
    # must be on for triggers to be enabled
    yield from bps.abs_set(zebra.inputs.soft_in_1, 1, group=group)
    yield from bps.abs_set(zebra.pc.gate_start, 0.5, group=group)
    # set rotation direction
    yield from bps.abs_set(zebra.pc.dir, RotationDirection.POSITIVE.value, group=group)
    # set gate width to total width
    yield from bps.abs_set(zebra.pc.gate_width, 1, group=group)
    # Set gate position to be angle of interest
    yield from bps.abs_set(zebra.pc.gate_trigger, axis.value, group=group)
    # Don't trigger the shutter
    yield from bps.abs_set(zebra.output.out_pvs[TTL_SHUTTER], DISCONNECT, group=group)
    # Trigger the detector with a pulse
    yield from bps.abs_set(zebra.output.out_pvs[TTL_DETECTOR], PC_PULSE, group=group)
    # Don't use the fluorescence detector
    yield from bps.abs_set(zebra.output.out_pvs[TTL_XSPRESS3], DISCONNECT, group=group)
    yield from bps.abs_set(zebra.output.pulse_1.input, DISCONNECT, group=group)
    LOGGER.info(f"ZEBRA SETUP: END - {'' if wait else 'not'} waiting for completion")
    if wait:
        yield from bps.wait(group)
