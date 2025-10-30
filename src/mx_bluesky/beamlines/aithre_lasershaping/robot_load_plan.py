from __future__ import annotations

from collections.abc import Generator
from datetime import datetime
from pathlib import Path

import bluesky.plan_stubs as bps
import pydantic
from blueapi.core import BlueskyContext
from bluesky.utils import Msg
from dodal.devices.motors import XYZOmegaStage, XYZStage
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.robot import BartRobot, SampleLocation

from mx_bluesky.common.device_setup_plans.robot_load_unload import (
    do_plan_while_lower_gonio_at_home,
)
from mx_bluesky.common.parameters.constants import DocDescriptorNames


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class RobotLoadComposite:
    # RobotLoad fields
    robot: BartRobot
    lower_gonio: XYZStage
    oav: OAV
    gonio: XYZOmegaStage


def create_devices(context: BlueskyContext) -> RobotLoadComposite:
    from mx_bluesky.common.utils.context import device_composite_from_context

    return device_composite_from_context(context, RobotLoadComposite)


def move_gonio_to_home_position(
    composite: RobotLoadComposite,
    x_home: float = 0.0,
    y_home: float = 0.0,
    z_home: float = 0.0,
    omega_home: float = 0.0,
    group: str = "group",
):
    """
    Move Gonio to home position, default is zero
    """
    yield from bps.abs_set(composite.gonio.omega, omega_home, group=group)
    yield from bps.abs_set(composite.gonio.x, x_home, group=group)
    yield from bps.abs_set(composite.gonio.y, y_home, group=group)
    yield from bps.abs_set(composite.gonio.z, z_home, group=group)

    yield from bps.wait(group=group)


def take_robot_snapshots(oav: OAV, directory: Path):
    time_now = datetime.now()
    snapshot_format = f"{time_now.strftime('%H%M%S')}_{{device}}_after_load"
    for device in [oav.snapshot]:
        yield from bps.abs_set(
            device.filename, snapshot_format.format(device=device.name)
        )
        yield from bps.abs_set(device.directory, str(directory))
        # Note: should be able to use `wait=True` after https://github.com/bluesky/bluesky/issues/1795
        yield from bps.trigger(device, group="snapshots")
        yield from bps.wait("snapshots")


def do_robot_load(
    composite: RobotLoadComposite,
    sample_location: SampleLocation,
    sample_id: int,
):
    yield from bps.abs_set(composite.robot.next_sample_id, sample_id, wait=True)
    yield from bps.abs_set(
        composite.robot,
        sample_location,
        group="robot_load",
    )

    move_gonio_to_home = move_gonio_to_home_position(
        composite=composite, group="robot_load"
    )

    gonio_in_position = yield from do_plan_while_lower_gonio_at_home(
        move_gonio_to_home, composite.lower_gonio
    )
    yield from bps.wait(gonio_in_position)


def pin_already_loaded(
    robot: BartRobot, sample_location: SampleLocation
) -> Generator[Msg, None, bool]:
    current_puck = yield from bps.rd(robot.current_puck)
    current_pin = yield from bps.rd(robot.current_pin)
    return (
        int(current_puck) == sample_location.puck
        and int(current_pin) == sample_location.pin
    )


def robot_unload(
    composite: RobotLoadComposite,
):
    """Unloads the currently mounted pin into the location that it was loaded from. The
    loaded location is stored on the robot and so need not be provided.
    """
    yield from move_gonio_to_home_position(composite)

    def _unload():
        yield from bps.trigger(composite.robot.unload, wait=True)

    gonio_finished = yield from do_plan_while_lower_gonio_at_home(
        _unload(), composite.lower_gonio
    )
    yield from bps.wait(gonio_finished)


def robot_load_and_snapshots(
    composite: RobotLoadComposite,
    location: SampleLocation,
    snapshot_directory: Path,
    sample_id: int,
):
    yield from bps.create(name=DocDescriptorNames.ROBOT_PRE_LOAD)
    yield from bps.read(composite.robot)
    yield from bps.save()

    robot_load_plan = do_robot_load(
        composite,
        location,
        sample_id,
    )

    gonio_finished = yield from do_plan_while_lower_gonio_at_home(
        robot_load_plan, composite.lower_gonio
    )
    yield from bps.wait(group="snapshot")

    yield from take_robot_snapshots(composite.oav, snapshot_directory)

    yield from bps.create(name=DocDescriptorNames.ROBOT_UPDATE)
    yield from bps.read(composite.robot)
    yield from bps.read(composite.oav.snapshot)
    yield from bps.save()

    yield from bps.wait(gonio_finished)
