from functools import partial

from bluesky import plan_stubs as bps
from bluesky.plans import rel_grid_scan
from bluesky.utils import short_uid
from dodal.beamlines.i23 import I23DetectorPositions
from dodal.common import inject
from dodal.devices.motors import SixAxisGonio
from dodal.devices.positioner import Positioner1D
from ophyd_async.epics.motor import Motor


def set_axis_to_max_velocity(axis: Motor):
    max_vel = yield from bps.rd(axis.max_velocity)
    yield from bps.mv(axis.velocity, max_vel)


def one_nd_step(
    detectors,
    step,
    pos_cache,
    omega_axis: Motor,
    omega_rotation: float,
    omega_velocity: float,
):
    def move():
        yield from bps.checkpoint()
        grp = short_uid("set")
        for motor, pos in step.items():
            yield from bps.abs_set(motor, pos, group=grp)
        yield from set_axis_to_max_velocity(omega_axis)
        yield from bps.abs_set(omega_axis, 0, group=grp)
        yield from bps.wait(group=grp)

    yield from move()
    yield from bps.mv(omega_axis.velocity, omega_velocity)
    yield from bps.mv(omega_axis, omega_rotation)


def serial_collection(
    x_steps: int,
    y_steps: int,
    x_step_size: float,
    y_step_size: float,
    omega_rotation: float,
    omega_velocity: float,
    detector_motion: Positioner1D = inject("detector_motion"),
    gonio: SixAxisGonio = inject("gonio"),
):
    """This plan runs a software controlled serial collection. i.e it moves in a snaked
    grid and does a small rotation collection at each point."""

    yield from bps.mv(detector_motion.stage_position, I23DetectorPositions.IN)
    yield from rel_grid_scan(
        [],
        gonio.y,
        0,
        y_step_size * (y_steps - 1),
        y_steps,
        gonio.x,
        0,
        x_step_size * (x_steps - 1),
        x_steps,
        per_step=partial(  # type: ignore
            one_nd_step,
            omega_axis=gonio.omega,
            omega_rotation=omega_rotation,
            omega_velocity=omega_velocity,
        ),
        snake_axes=True,
    )
