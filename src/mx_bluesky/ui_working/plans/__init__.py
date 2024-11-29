import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
from blueapi.core import MsgGenerator
from dodal.devices.i24.vgonio import VerticalGoniometer
from ophyd_async.core import (
    callback_on_mock_put,
    set_mock_value,
)
from ophyd_async.epics.motor import Motor

from mx_bluesky.hyperion.log import LOGGER
from mx_bluesky.ui_working import devices

DEVICES = None


def patch_motor(motor: Motor, initial_position=0):
    set_mock_value(motor.user_setpoint, initial_position)
    set_mock_value(motor.user_readback, initial_position)
    set_mock_value(motor.deadband, 0.001)
    set_mock_value(motor.motor_done_move, 1)
    set_mock_value(motor.velocity, 3)
    return callback_on_mock_put(
        motor.user_setpoint,
        lambda pos, *args, **kwargs: set_mock_value(motor.user_readback, pos),
    )


def create_devices():
    global DEVICES
    if DEVICES is None:
        gon = devices.vgonio()
        patch_motor(gon.x)
        patch_motor(gon.yh)
        patch_motor(gon.z)
        patch_motor(gon.omega)
        DEVICES = {"gonio": gon}

    return DEVICES


@bpp.run_decorator()
def virtual_relative_move_px(
    x_px: float,
    y_px: float,
    x_pixels_per_micron: float,
    y_pixels_per_micron: float,
) -> MsgGenerator:
    """
    Used for click-to-move on an OAV. Moves the gonio a relative distance of x and y to
    bring the clicked location to the beam centre. Takes account of the goniometer omega
    position in order to do the relative move in the lab frame.
    """
    gonio = create_devices()["gonio"]

    yield from virtual_relative_move_um(
        x_px / x_pixels_per_micron, y_px / y_pixels_per_micron
    )


@bpp.run_decorator()
def virtual_relative_move_um(x_um: float, y_um: float) -> MsgGenerator:
    """
    Used for click-to-move on an OAV. Moves the gonio a relative distance of x and y to
    bring the clicked location to the beam centre. Takes account of the goniometer omega
    position in order to do the relative move in the lab frame.
    """
    gonio = create_devices()["gonio"]

    LOGGER.info(
        f"Current position: {yield from bps.rd(gonio.x)}, {yield from bps.rd(gonio.yh)}"
    )
    yield from bps.rel_set(gonio.x, x_um, wait=True)
    yield from bps.rel_set(gonio.yh, y_um, wait=True)
    LOGGER.info(
        f"New position: {yield from bps.rd(gonio.x)}, {yield from bps.rd(gonio.yh)}"
    )


@bpp.run_decorator()
def rotate_omega(move_deg: float) -> MsgGenerator:
    """
    Used for click-to-move on an OAV. Moves the gonio a relative distance of x and y to
    bring the clicked location to the beam centre. Takes account of the goniometer omega
    position in order to do the relative move in the lab frame.
    """
    gonio = create_devices()["gonio"]

    yield from bps.mvr(gonio.omega, move_deg)


@bpp.run_decorator()
def sleep(sec: int) -> MsgGenerator:
    for i in range(sec):
        yield from bps.sleep(1)
