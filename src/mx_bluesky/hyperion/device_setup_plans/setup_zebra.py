import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.devices.zebra.zebra import (
    ArmDemand,
    EncEnum,
    I03Axes,
    RotationDirection,
    Zebra,
)
from dodal.devices.zebra.zebra_controlled_shutter import (
    ZebraShutter,
    ZebraShutterControl,
)

from mx_bluesky.common.utils.log import LOGGER

ZEBRA_STATUS_TIMEOUT = 30


def arm_zebra(zebra: Zebra):
    yield from bps.abs_set(zebra.pc.arm, ArmDemand.ARM, wait=True)


def tidy_up_zebra_after_rotation_scan(
    zebra: Zebra,
    zebra_shutter: ZebraShutter,
    group="tidy_up_zebra_after_rotation",
    wait=True,
):
    yield from bps.abs_set(zebra.pc.arm, ArmDemand.DISARM, group=group)
    yield from bps.abs_set(
        zebra_shutter.control_mode, ZebraShutterControl.MANUAL, group=group
    )
    if wait:
        yield from bps.wait(group, timeout=ZEBRA_STATUS_TIMEOUT)


def set_shutter_auto_input(zebra: Zebra, input: int, group="set_shutter_trigger"):
    """Set the signal that controls the shutter. We use the second input to the
    Zebra's AND2 gate for this input. ZebraShutter control mode must be in auto for this input to take control

    For more details see the ZebraShutter device."""
    auto_gate = zebra.mapping.AND_GATE_FOR_AUTO_SHUTTER
    auto_shutter_control = zebra.logic_gates.and_gates[auto_gate]
    yield from bps.abs_set(auto_shutter_control.sources[2], input, group)


def configure_zebra_and_shutter_for_auto_shutter(
    zebra: Zebra, zebra_shutter: ZebraShutter, input: int, group="use_automatic_shutter"
):
    """Set the shutter to auto mode, and configure the zebra to trigger the shutter on
    an input source. For the input, use one of the source constants in zebra.py

    When the shutter is in auto/manual, logic in EPICS sets the Zebra's
    SOFT_IN1 to low/high respectively. The Zebra's AND2 gate should be used to control the shutter while in auto mode.
    To do this, we need (AND2 = SOFT_IN1 AND input), where input is the zebra signal we want to control the shutter when in auto mode.
    """
    # See https://github.com/DiamondLightSource/dodal/issues/813 for better typing here.

    # Set shutter to auto mode
    yield from bps.abs_set(
        zebra_shutter.control_mode, ZebraShutterControl.AUTO, group=group
    )

    auto_gate = zebra.mapping.AND_GATE_FOR_AUTO_SHUTTER

    # Set first input of AND2 gate to SOFT_IN1, which is high when shutter is in auto mode
    # Note the Zebra should ALWAYS be setup this way. See https://github.com/DiamondLightSource/mx-bluesky/issues/551
    yield from bps.abs_set(
        zebra.logic_gates.and_gates[auto_gate].sources[1],
        zebra.mapping.sources.SOFT_IN1,
        group=group,
    )

    # Set the second input of AND2 gate to the requested zebra input source
    yield from set_shutter_auto_input(zebra, input, group=group)


def setup_zebra_for_rotation(
    zebra: Zebra,
    zebra_shutter: ZebraShutter,
    axis: EncEnum = I03Axes.OMEGA,
    start_angle: float = 0,
    scan_width: float = 360,
    shutter_opening_deg: float = 2.5,
    shutter_opening_s: float = 0.04,
    direction: RotationDirection = RotationDirection.POSITIVE,
    group: str = "setup_zebra_for_rotation",
    wait: bool = True,
):
    """Set up the Zebra to collect a rotation dataset. Any plan using this is
    responsible for setting the smargon velocity appropriately so that the desired
    image width is achieved with the exposure time given here.

    Parameters:
        zebra:              The zebra device to use
        axis:               I03 axes enum representing which axis to use for position
                            compare. Currently always omega.
        start_angle:        Position at which the scan should begin, in degrees.
        scan_width:         Total angle through which to collect, in degrees.
        shutter_opening_deg:How many degrees of rotation it takes for the fast shutter
                            to open. Increases the gate width.
        shutter_opening_s:  How many seconds it takes for the fast shutter to open. The
                            detector pulse is delayed after the shutter signal by this
                            amount.
        direction:          RotationDirection enum for positive or negative.
                            Defaults to Positive.
        group:              A name for the group of statuses generated
        wait:               Block until all the settings have completed
    """

    if not isinstance(direction, RotationDirection):
        raise ValueError(
            "Disallowed rotation direction provided to Zebra setup plan. "
            "Use RotationDirection.POSITIVE or RotationDirection.NEGATIVE."
        )
    yield from bps.abs_set(zebra.pc.dir, direction.value, group=group)
    LOGGER.info("ZEBRA SETUP: START")
    # Set gate start, adjust for shutter opening time if necessary
    LOGGER.info(f"ZEBRA SETUP: degrees to adjust for shutter = {shutter_opening_deg}")
    LOGGER.info(f"ZEBRA SETUP: start angle start: {start_angle}")
    LOGGER.info(f"ZEBRA SETUP: start angle adjusted, gate start set to: {start_angle}")
    yield from bps.abs_set(zebra.pc.gate_start, start_angle, group=group)
    # set gate width to total width
    yield from bps.abs_set(
        zebra.pc.gate_width, scan_width + shutter_opening_deg, group=group
    )
    LOGGER.info(
        f"Pulse start set to shutter open time, set to: {abs(shutter_opening_s)}"
    )
    yield from bps.abs_set(zebra.pc.pulse_start, abs(shutter_opening_s), group=group)
    # Set gate position to be angle of interest
    yield from bps.abs_set(zebra.pc.gate_trigger, axis.value, group=group)
    # Set shutter to automatic and to trigger via PC_GATE
    yield from configure_zebra_and_shutter_for_auto_shutter(
        zebra, zebra_shutter, zebra.mapping.sources.PC_GATE, group=group
    )
    # Trigger the detector with a pulse
    yield from bps.abs_set(
        zebra.output.out_pvs[zebra.mapping.outputs.TTL_DETECTOR],
        zebra.mapping.sources.PC_PULSE,
        group=group,
    )
    # Don't use the fluorescence detector
    yield from bps.abs_set(
        zebra.output.out_pvs[zebra.mapping.outputs.TTL_XSPRESS3],
        zebra.mapping.sources.DISCONNECT,
        group=group,
    )
    yield from bps.abs_set(
        zebra.output.pulse_1.input, zebra.mapping.sources.DISCONNECT, group=group
    )
    LOGGER.info(f"ZEBRA SETUP: END - {'' if wait else 'not'} waiting for completion")
    if wait:
        yield from bps.wait(group, timeout=ZEBRA_STATUS_TIMEOUT)


def setup_zebra_for_gridscan(
    zebra: Zebra,
    zebra_shutter: ZebraShutter,
    group="setup_zebra_for_gridscan",
    wait=True,
):
    # Set shutter to automatic and to trigger via motion controller GPIO signal (IN4_TTL)
    yield from configure_zebra_and_shutter_for_auto_shutter(
        zebra, zebra_shutter, zebra.mapping.sources.IN4_TTL, group=group
    )

    yield from bps.abs_set(
        zebra.output.out_pvs[zebra.mapping.outputs.TTL_DETECTOR],
        zebra.mapping.sources.IN3_TTL,
        group=group,
    )
    yield from bps.abs_set(
        zebra.output.out_pvs[zebra.mapping.outputs.TTL_XSPRESS3],
        zebra.mapping.sources.DISCONNECT,
        group=group,
    )
    yield from bps.abs_set(
        zebra.output.pulse_1.input, zebra.mapping.sources.DISCONNECT, group=group
    )

    if wait:
        yield from bps.wait(group, timeout=ZEBRA_STATUS_TIMEOUT)


def tidy_up_zebra_after_gridscan(
    zebra: Zebra,
    zebra_shutter: ZebraShutter,
    group="tidy_up_zebra_after_gridscan",
    wait=True,
) -> MsgGenerator:
    yield from bps.abs_set(
        zebra.output.out_pvs[zebra.mapping.outputs.TTL_DETECTOR],
        zebra.mapping.sources.PC_PULSE,
        group=group,
    )
    yield from bps.abs_set(
        zebra_shutter.control_mode, ZebraShutterControl.MANUAL, group=group
    )
    yield from set_shutter_auto_input(zebra, zebra.mapping.sources.PC_GATE, group=group)

    if wait:
        yield from bps.wait(group, timeout=ZEBRA_STATUS_TIMEOUT)


def setup_zebra_for_panda_flyscan(
    zebra: Zebra,
    zebra_shutter: ZebraShutter,
    group="setup_zebra_for_panda_flyscan",
    wait=True,
):
    # Forwards eiger trigger signal from panda
    yield from bps.abs_set(
        zebra.output.out_pvs[zebra.mapping.outputs.TTL_DETECTOR],
        zebra.mapping.sources.IN1_TTL,
        group=group,
    )

    # Set shutter to automatic and to trigger via motion controller GPIO signal (IN4_TTL)
    yield from configure_zebra_and_shutter_for_auto_shutter(
        zebra, zebra_shutter, zebra.mapping.sources.IN4_TTL, group=group
    )

    yield from bps.abs_set(
        zebra.output.out_pvs[zebra.mapping.outputs.TTL_XSPRESS3],
        zebra.mapping.sources.DISCONNECT,
        group=group,
    )

    yield from bps.abs_set(
        zebra.output.out_pvs[zebra.mapping.outputs.TTL_PANDA],
        zebra.mapping.sources.IN3_TTL,
        group=group,
    )  # Tells panda that motion is beginning/changing direction

    if wait:
        yield from bps.wait(group, timeout=ZEBRA_STATUS_TIMEOUT)
