import bluesky.plan_stubs as bps
from dodal.devices.zebra.zebra import (
    ArmDemand,
    EncEnum,
    I03Axes,
    RotationDirection,
    Zebra,
)
from dodal.devices.zebra.zebra_constants_mapping import UnmappedZebraException
from dodal.devices.zebra.zebra_controlled_shutter import (
    ZebraShutter,
    ZebraShutterControl,
)

from mx_bluesky.common.device_setup_plans.setup_zebra_and_shutter import (
    configure_zebra_and_shutter_for_auto_shutter,
)
from mx_bluesky.common.parameters.constants import ZEBRA_STATUS_TIMEOUT
from mx_bluesky.common.utils.log import LOGGER


def arm_zebra(zebra: Zebra):
    LOGGER.info("Arming zebra position compare...")
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

    # Don't use the fluorescence detector if connected
    try:
        yield from bps.abs_set(
            zebra.output.out_pvs[zebra.mapping.outputs.TTL_XSPRESS3],
            zebra.mapping.sources.DISCONNECT,
            group=group,
        )
    except UnmappedZebraException:
        ...
    yield from bps.abs_set(
        zebra.output.pulse_1.input, zebra.mapping.sources.DISCONNECT, group=group
    )
    LOGGER.info(f"ZEBRA SETUP: END - {'' if wait else 'not'} waiting for completion")
    if wait:
        yield from bps.wait(group, timeout=ZEBRA_STATUS_TIMEOUT)
