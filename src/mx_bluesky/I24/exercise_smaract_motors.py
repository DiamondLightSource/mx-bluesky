from __future__ import annotations

from collections import namedtuple

import bluesky.plan_stubs as bps

# from bluesky import RunEngine
from dodal.devices.i24.i24_vgonio import VGonio

Point3D = namedtuple("Point3D", ("x", "y", "z"))


def check_motor_position(motor):
    current_pos = yield from bps.rd(motor)
    print(current_pos)
    pass


def exercise_motor(motor, min_pos, max_pos):
    yield from bps.mv(motor, max_pos)
    # check
    yield from bps.mv(motor, min_pos)


def move_xz_motors(smaract_motors: VGonio, pos: float, iter: int = 10):
    yield from bps.mv()
    # exercise_motor
    # 10 times
    # move back to 0


def move_omega(smaract_motors: VGonio, pos: float = 0.0):
    yield from bps.mv(smaract_motors.omega, pos, wait=True)
    # check that it actually arrived


def exercise_plan(smaract: VGonio):
    yield from move_omega(smaract, 45.0)
    # exercise x and z here
    yield from move_omega(smaract, 0.0)
    pass


def main():
    # RE = RunEngine()
    # RE(exercise_plan())
    pass


main()
