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

from mx_bluesky.common.parameters.constants import ZEBRA_STATUS_TIMEOUT


@runtime_checkable
class GridscanSetupDevices(Protocol):
    zebra: Zebra
    sample_shutter: ZebraShutter


def setup_zebra_for_gridscan(
    composite: GridscanSetupDevices,  # XRC gridscan's generic trigger setup expects a composite rather than individual devices
    group="setup_zebra_for_gridscan",
    wait=True,
) -> MsgGenerator:
    zebra = composite.zebra
    # Set shutter to automatic and to trigger via motion controller GPIO signal (IN4_TTL)
    yield from configure_zebra_and_shutter_for_auto_shutter(
        zebra, composite.sample_shutter, zebra.mapping.sources.IN4_TTL, group=group
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
