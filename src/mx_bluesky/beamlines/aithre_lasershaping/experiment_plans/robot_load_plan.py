from __future__ import annotations

from datetime import datetime
from pathlib import Path

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
import pydantic
from dodal.devices.motors import XYZOmegaStage, XYZStage
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.oav.pin_image_recognition import PinTipDetection
from dodal.devices.robot import BartRobot, SampleLocation

from mx_bluesky.beamlines.aithre_lasershaping.parameters.constants import CONST
from mx_bluesky.beamlines.aithre_lasershaping.parameters.robot_load_parameters import (
    AithreRobotLoad,
)
from mx_bluesky.common.device_setup_plans.robot_load_unload import (
    do_plan_while_lower_gonio_at_home,
)
from mx_bluesky.common.experiment_plans.pin_tip_centring_plan import (
    PinTipCentringComposite,
    pin_tip_centre_plan,
)
from mx_bluesky.common.parameters.constants import (
    DocDescriptorNames,
    PlanNameConstants,
)


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class RobotLoadComposite:
    # RobotLoad fields
    robot: BartRobot
    lower_gonio: XYZStage
    oav: OAV
    gonio: XYZOmegaStage


def _move_gonio_to_home_position(
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


def _take_robot_snapshots(oav: OAV, directory: Path):
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


def _do_robot_load_and_centre(
    composite: RobotLoadComposite,
    sample_location: SampleLocation,
    sample_id: int,
    pin_tip_detection: PinTipDetection,
    tip_offset_microns: float = 0,
    oav_config_file: str = CONST.OAV_CENTRING_FILE,
):
    yield from bps.abs_set(composite.robot.next_sample_id, sample_id, wait=True)
    yield from bps.abs_set(
        composite.robot,
        sample_location,
        group="robot_load",
    )

    yield from _move_gonio_to_home_position(composite=composite, group="robot_load")

    yield from bps.wait(group="robot_load")

    pin_tip_centring_composite = PinTipCentringComposite(
        composite.oav, composite.gonio, pin_tip_detection
    )
    yield from pin_tip_centre_plan(
        pin_tip_centring_composite, tip_offset_microns, oav_config_file
    )


def _robot_load_and_snapshots(
    composite: RobotLoadComposite,
    location: SampleLocation,
    snapshot_directory: Path,
    sample_id: int,
    pin_tip_detection: PinTipDetection,
    tip_offset_microns: float = 0,
    oav_config_file: str = CONST.OAV_CENTRING_FILE,
):
    yield from bps.create(name=DocDescriptorNames.ROBOT_PRE_LOAD)
    yield from bps.read(composite.robot)
    yield from bps.save()

    robot_load_plan = _do_robot_load_and_centre(
        composite,
        location,
        sample_id,
        pin_tip_detection,
        tip_offset_microns,
        oav_config_file,
    )

    gonio_finished = yield from do_plan_while_lower_gonio_at_home(
        robot_load_plan, composite.lower_gonio
    )
    yield from bps.wait(group="snapshot")

    yield from _take_robot_snapshots(composite.oav, snapshot_directory)

    yield from bps.create(name=DocDescriptorNames.ROBOT_UPDATE)
    yield from bps.read(composite.robot)
    yield from bps.read(composite.oav.snapshot)
    yield from bps.save()

    yield from bps.wait(gonio_finished)


def robot_load_and_snapshots_plan(
    composite: RobotLoadComposite,
    params: AithreRobotLoad,
    ptd: PinTipDetection,
    tip_offset_microns: float = 0,
    oav_config_file: str = CONST.OAV_CENTRING_FILE,
):
    assert params.sample_puck is not None
    assert params.sample_pin is not None

    sample_location = SampleLocation(params.sample_puck, params.sample_pin)

    yield from _move_gonio_to_home_position(composite)

    yield from bpp.set_run_key_wrapper(
        bpp.run_wrapper(
            _robot_load_and_snapshots(
                composite,
                sample_location,
                params.snapshot_directory,
                params.sample_id,
                ptd,
                tip_offset_microns,
                oav_config_file,
            ),
            md={
                "subplan_name": PlanNameConstants.ROBOT_LOAD,
                "metadata": {"visit": params.visit, "sample_id": params.sample_id},
                "activate_callbacks": [
                    "RobotLoadISPyBCallback",
                ],
            },
        ),
        PlanNameConstants.ROBOT_LOAD_AND_SNAPSHOTS,
    )


def robot_unload_plan(
    composite: RobotLoadComposite,
    params: AithreRobotLoad,
):
    @bpp.run_decorator(
        md={
            "subplan_name": PlanNameConstants.ROBOT_UNLOAD,
            "metadata": {"visit": params.visit, "sample_id": params.sample_id},
            "activate_callbacks": [
                "RobotLoadISPyBCallback",
            ],
        },
    )
    def do_robot_unload_and_send_to_ispyb():
        yield from _take_robot_snapshots(composite.oav, params.snapshot_directory)
        yield from bps.wait(group="snapshot")
        yield from _move_gonio_to_home_position(composite)

        yield from bps.abs_set(composite.robot, None, wait=True)

        yield from bps.create(name=DocDescriptorNames.ROBOT_UPDATE)
        yield from bps.read(composite.robot)
        yield from bps.read(composite.oav.snapshot)
        yield from bps.save()

    yield from do_robot_unload_and_send_to_ispyb()
