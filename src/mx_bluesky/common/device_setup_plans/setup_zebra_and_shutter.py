from typing import Protocol, runtime_checkable

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

from mx_bluesky.common.parameters.constants import ZEBRA_STATUS_TIMEOUT
from mx_bluesky.common.utils.log import LOGGER

"""Plans in this file will work as intended if the zebra has the following configuration:
- A fast shutter is connected through TTL inputs from the Zebra.
- When the zebra shutter is set to auto mode, the IOC sets the Zebra's SOFT_IN1 signal high.
- When the zebra shutter is set to manual mode, the IOC sets the Zebra's SOFT_IN1 signal low.
"""


@runtime_checkable
class GridscanSetupDevices(Protocol):
    zebra: Zebra
    sample_shutter: ZebraShutter


def setup_zebra_for_gridscan(
    composite: GridscanSetupDevices,  # XRC gridscan's generic trigger setup expects a composite rather than individual devices
    group="setup_zebra_for_gridscan",
    wait=True,
    ttl_input_for_detector_to_use: None | int = None,
) -> MsgGenerator:
    """
    Configure the zebra for an MX XRC gridscan by allowing the zebra to trigger the fast shutter and detector via signals
    sent from the motion controller.

    Args:
        composite: Composite device containing a zebra and zebra shutter
        group: Bluesky group to use when waiting on completion
        wait: If true, block until completion
        ttl_input_for_detector_to_use: If the zebra isn't using the TTL_DETECTOR zebra input, manually
        specify which TTL input is being used for the desired detector

    This plan assumes that the motion controller, as part of its gridscan PLC, will send triggers as required to the zebra's
    IN4_TTL and IN3_TTL to control the fast_shutter and detector respectively

    """
    zebra = composite.zebra
    ttl_detector = ttl_input_for_detector_to_use or zebra.mapping.outputs.TTL_DETECTOR
    # Set shutter to automatic and to trigger via motion controller GPIO signal (IN4_TTL)
    yield from configure_zebra_and_shutter_for_auto_shutter(
        zebra, composite.sample_shutter, zebra.mapping.sources.IN4_TTL, group=group
    )

    yield from bps.abs_set(
        zebra.output.out_pvs[ttl_detector],
        zebra.mapping.sources.IN3_TTL,
        group=group,
    )

    if wait:
        yield from bps.wait(group, timeout=ZEBRA_STATUS_TIMEOUT)


def set_shutter_auto_input(zebra: Zebra, input: int, group="set_shutter_trigger"):
    """Set the signal that controls the shutter. We use the second input to the
    Zebra's AND_GATE_FOR_AUTO_SHUTTER for this input. ZebraShutter control mode must be in auto for this input to take control

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
    SOFT_IN1 to low/high respectively. The Zebra's AND_GATE_FOR_AUTO_SHUTTER should be used to control the shutter while in auto mode.
    To do this, we need (AND_GATE_FOR_AUTO_SHUTTER = SOFT_IN1 AND input), where input is the zebra signal we want to control the shutter when in auto mode.
    """

    # Set shutter to auto mode
    yield from bps.abs_set(
        zebra_shutter.control_mode, ZebraShutterControl.AUTO, group=group
    )

    auto_gate = zebra.mapping.AND_GATE_FOR_AUTO_SHUTTER

    # Set first input of AND_GATE_FOR_AUTO_SHUTTER to SOFT_IN1, which is high when shutter is in auto mode
    # Note the Zebra should ALWAYS be setup this way. See https://github.com/DiamondLightSource/mx-bluesky/issues/551
    yield from bps.abs_set(
        zebra.logic_gates.and_gates[auto_gate].sources[1],
        zebra.mapping.sources.SOFT_IN1,
        group=group,
    )

    # Set the second input of AND_GATE_FOR_AUTO_SHUTTER to the requested zebra input source
    yield from set_shutter_auto_input(zebra, input, group=group)


def tidy_up_zebra_after_gridscan(
    zebra: Zebra,
    zebra_shutter: ZebraShutter,
    group="tidy_up_zebra_after_gridscan",
    wait=True,
    ttl_input_for_detector_to_use: int | None = None,
) -> MsgGenerator:
    """
    Set the zebra back to a state which is expected by GDA.

    Args:
        zebra: Zebra device.
        zebra_shutter: Zebra shutter device.
        group: Bluesky group to use when waiting on completion.
        wait: If true, block until completion.
        ttl_input_for_detector_to_use: If the zebra isn't using the TTL_DETECTOR zebra input, manually
        specify which TTL input is being used for the desired detector.
    """

    LOGGER.info("Tidying up Zebra")

    ttl_detector = ttl_input_for_detector_to_use or zebra.mapping.outputs.TTL_DETECTOR

    yield from bps.abs_set(
        zebra.output.out_pvs[ttl_detector],
        zebra.mapping.sources.PC_PULSE,
        group=group,
    )
    yield from bps.abs_set(
        zebra_shutter.control_mode, ZebraShutterControl.MANUAL, group=group
    )
    yield from set_shutter_auto_input(zebra, zebra.mapping.sources.PC_GATE, group=group)

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
    ttl_input_for_detector_to_use: int | None = None,
):
    """Set up the Zebra to collect a rotation dataset. Any plan using this is
    responsible for setting the smargon velocity appropriately so that the desired
    image width is achieved with the exposure time given here.

    Parameters:
        zebra:              The zebra device to use
        axis:               Encoder enum representing which axis to use for position
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
        ttl_input_for_detector_to_use: If the zebra isn't using the TTL_DETECTOR zebra input,
                            manually specify which TTL input is being used for the desired detector
    """

    ttl_detector = ttl_input_for_detector_to_use or zebra.mapping.outputs.TTL_DETECTOR

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
        zebra.output.out_pvs[ttl_detector],
        zebra.mapping.sources.PC_PULSE,
        group=group,
    )

    LOGGER.info(f"ZEBRA SETUP: END - {'' if wait else 'not'} waiting for completion")
    if wait:
        yield from bps.wait(group, timeout=ZEBRA_STATUS_TIMEOUT)


def tidy_up_zebra_after_rotation_scan(
    zebra: Zebra,
    zebra_shutter: ZebraShutter,
    group="tidy_up_zebra_after_rotation",
    wait=True,
):
    """
    Set the zebra back to a state which is expected by GDA.

    Args:
        zebra: Zebra device.
        zebra_shutter: Zebra shutter device.
        group: Bluesky group to use when waiting on completion.
        wait: If true, block until completion.
    """

    yield from bps.abs_set(zebra.pc.arm, ArmDemand.DISARM, group=group)
    yield from bps.abs_set(
        zebra_shutter.control_mode, ZebraShutterControl.MANUAL, group=group
    )
    if wait:
        yield from bps.wait(group, timeout=ZEBRA_STATUS_TIMEOUT)
