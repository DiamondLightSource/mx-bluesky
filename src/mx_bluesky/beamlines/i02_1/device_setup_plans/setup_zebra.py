from collections.abc import Callable
from functools import wraps

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
from bluesky.utils import MsgGenerator
from dodal.devices.zebra import (
    AUTO_SHUTTER_GATE,
    AUTO_SHUTTER_INPUT_2,
    PC_GATE,
    PC_PULSE,
    TTL_DETECTOR,
    ArmDemand,
    Zebra,
)
from dodal.devices.zebra_controlled_shutter import ZebraShutter, ZebraShutterControl

from mx_bluesky.common.utils.log import LOGGER

ZEBRA_STATUS_TIMEOUT = 30


def bluesky_retry(func: Callable):
    """Decorator that will retry the decorated plan if it fails.

    Use this with care as it knows nothing about the state of the world when things fail.
    If it is possible that your plan fails when the beamline is in a transient state that
    the plan could not act on do not use this decorator without doing some more intelligent
    clean up.

    You should avoid using this decorator often in general production as it hides errors,
    instead it should be used only for debugging these underlying errors.
    """

    @wraps(func)
    def newfunc(*args, **kwargs):
        def log_and_retry(exception):
            LOGGER.error(f"Function {func.__name__} failed with {exception}, retrying")
            yield from func(*args, **kwargs)

        yield from bpp.contingency_wrapper(
            func(*args, **kwargs), except_plan=log_and_retry, auto_raise=False
        )

    return newfunc


def arm_zebra(zebra: Zebra):
    yield from bps.abs_set(zebra.pc.arm, ArmDemand.ARM, wait=True)  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809


def tidy_up_zebra_after_rotation_scan(
    zebra: Zebra,
    zebra_shutter: ZebraShutter,
    group="tidy_up_zebra_after_rotation",
    wait=True,
):
    yield from bps.abs_set(zebra.pc.arm, ArmDemand.DISARM, group=group)  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
    yield from bps.abs_set(
        zebra_shutter.control_mode, ZebraShutterControl.MANUAL, group=group
    )
    if wait:
        yield from bps.wait(group, timeout=ZEBRA_STATUS_TIMEOUT)


def set_shutter_auto_input(zebra: Zebra, input: int, group="set_shutter_trigger"):
    """Set the signal that controls the shutter. We use the second input to the
    Zebra's AND2 gate for this input. ZebraShutter control mode must be in auto for this input to take control

    For more details see the ZebraShutter device."""
    auto_shutter_control = zebra.logic_gates.and_gates[AUTO_SHUTTER_GATE]
    yield from bps.abs_set(
        auto_shutter_control.sources[AUTO_SHUTTER_INPUT_2], input, group
    )


# TODO: needed for vmxm?
def configure_zebra_and_shutter_for_auto_shutter(
    zebra: Zebra, zebra_shutter: ZebraShutter, input: int, group="use_automatic_shutter"
): ...


@bluesky_retry
def setup_zebra_for_gridscan(
    zebra: Zebra,
    zebra_shutter: ZebraShutter,
    group="setup_zebra_for_gridscan",
    wait=True,
): ...


@bluesky_retry
def tidy_up_zebra_after_gridscan(
    zebra: Zebra,
    zebra_shutter: ZebraShutter,
    group="tidy_up_zebra_after_gridscan",
    wait=True,
) -> MsgGenerator:
    yield from bps.abs_set(zebra.output.out_pvs[TTL_DETECTOR], PC_PULSE, group=group)
    yield from bps.abs_set(
        zebra_shutter.control_mode, ZebraShutterControl.MANUAL, group=group
    )
    yield from set_shutter_auto_input(zebra, PC_GATE, group=group)

    if wait:
        yield from bps.wait(group, timeout=ZEBRA_STATUS_TIMEOUT)
