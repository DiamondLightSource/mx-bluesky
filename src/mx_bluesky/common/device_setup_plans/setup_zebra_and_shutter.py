from typing import Protocol, runtime_checkable

import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.devices.zebra.zebra import (
    Zebra,
)
from dodal.devices.zebra.zebra_controlled_shutter import (
    ZebraShutter,
    ZebraShutterControl,
)
from ophyd_async.core import SignalRW

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
    zebra_output_to_disconnect: None | SignalRW = None,
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
        zebra_output_to_disconnect: Optionally specify a TTL output which should be unmapped (disconnected) from the Zebras inputs
        before the gridscan begins.

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

    if zebra_output_to_disconnect:
        yield from bps.abs_set(
            zebra_output_to_disconnect, zebra.mapping.sources.DISCONNECT, group
        )

    yield from bps.abs_set(
        zebra.output.pulse_1.input, zebra.mapping.sources.DISCONNECT, group=group
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

    # Set first input of AND gate to SOFT_IN1, which is high when shutter is in auto mode
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
    ttl_input_for_detector_to_use=None,
) -> MsgGenerator:
    """
    Set the zebra back to a state which is expected by GDA

    If the Zebra has multiple detectors connected, you must manually specify which TTL input connects to your desired detector
    in the ttl_input_for_detector_to_use parameter.
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
