from __future__ import annotations

from collections.abc import Generator
from datetime import datetime
from pathlib import Path
from typing import cast

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
import pydantic
from blueapi.core import BlueskyContext
from bluesky.utils import Msg
from dodal.devices.aperturescatterguard import ApertureScatterguard
from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
from dodal.devices.backlight import Backlight, BacklightPosition
from dodal.devices.focusing_mirror import FocusingMirrorWithStripes, MirrorVoltages
from dodal.devices.i03.dcm import DCM
from dodal.devices.i03.undulator_dcm import UndulatorDCM
from dodal.devices.motors import XYZPositioner
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.robot import BartRobot, SampleLocation
from dodal.devices.smargon import Smargon
from dodal.devices.thawer import Thawer
from dodal.devices.webcam import Webcam
from dodal.devices.xbpm_feedback import XBPMFeedback

from mx_bluesky.common.device_setup_plans.robot_load_unload import (
    do_plan_while_lower_gonio_at_home,
    prepare_for_robot_load,
    wait_for_smargon_not_disabled,
)
from mx_bluesky.hyperion.experiment_plans.set_energy_plan import (
    SetEnergyComposite,
    set_energy_plan,
)
from mx_bluesky.hyperion.parameters.constants import CONST
from mx_bluesky.hyperion.parameters.robot_load import RobotLoadAndEnergyChange


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class RobotLoadAndEnergyChangeComposite:
    # SetEnergyComposite fields
    vfm: FocusingMirrorWithStripes
    mirror_voltages: MirrorVoltages
    dcm: DCM
    undulator_dcm: UndulatorDCM
    xbpm_feedback: XBPMFeedback
    attenuator: BinaryFilterAttenuator

    # RobotLoad fields
    robot: BartRobot
    webcam: Webcam
    lower_gonio: XYZPositioner
    thawer: Thawer
    oav: OAV
    smargon: Smargon
    aperture_scatterguard: ApertureScatterguard
    backlight: Backlight


def create_devices(context: BlueskyContext) -> RobotLoadAndEnergyChangeComposite:
    from mx_bluesky.common.utils.context import device_composite_from_context

    return device_composite_from_context(context, RobotLoadAndEnergyChangeComposite)


def take_robot_snapshots(oav: OAV, webcam: Webcam, directory: Path):
    time_now = datetime.now()
    snapshot_format = f"{time_now.strftime('%H%M%S')}_{{device}}_after_load"
    for device in [oav.snapshot, webcam]:
        yield from bps.abs_set(
            device.filename, snapshot_format.format(device=device.name)
        )
        yield from bps.abs_set(device.directory, str(directory))
        # Note: should be able to use `wait=True` after https://github.com/bluesky/bluesky/issues/1795
        yield from bps.trigger(device, group="snapshots")
        yield from bps.wait("snapshots")


def do_robot_load(
    composite: RobotLoadAndEnergyChangeComposite,
    sample_location: SampleLocation,
    demand_energy_ev: float | None,
    thawing_time: float,
):
    yield from bps.abs_set(
        composite.robot,
        sample_location,
        group="robot_load",
    )

    yield from set_energy_plan(demand_energy_ev, cast(SetEnergyComposite, composite))

    yield from bps.wait("robot_load")

    yield from bps.abs_set(
        composite.thawer.thaw_for_time_s,
        thawing_time,
        group="thawing_finished",
    )
    yield from wait_for_smargon_not_disabled(composite.smargon)


def pin_already_loaded(
    robot: BartRobot, sample_location: SampleLocation
) -> Generator[Msg, None, bool]:
    current_puck = yield from bps.rd(robot.current_puck)
    current_pin = yield from bps.rd(robot.current_pin)
    return (
        int(current_puck) == sample_location.puck
        and int(current_pin) == sample_location.pin
    )


def robot_load_and_snapshots(
    composite: RobotLoadAndEnergyChangeComposite,
    location: SampleLocation,
    snapshot_directory: Path,
    thawing_time: float,
    demand_energy_ev: float | None,
):
    yield from bps.abs_set(composite.backlight, BacklightPosition.IN, group="snapshot")

    robot_load_plan = do_robot_load(
        composite,
        location,
        demand_energy_ev,
        thawing_time,
    )

    gonio_finished = yield from do_plan_while_lower_gonio_at_home(
        robot_load_plan, composite.lower_gonio
    )
    yield from bps.wait(group="snapshot")

    yield from take_robot_snapshots(composite.oav, composite.webcam, snapshot_directory)

    yield from bps.create(name=CONST.DESCRIPTORS.ROBOT_LOAD)
    yield from bps.read(composite.robot.barcode)
    yield from bps.read(composite.oav.snapshot)
    yield from bps.read(composite.webcam)
    yield from bps.save()

    yield from bps.wait(gonio_finished)


def robot_load_and_change_energy_plan(
    composite: RobotLoadAndEnergyChangeComposite,
    params: RobotLoadAndEnergyChange,
):
    assert params.sample_puck is not None
    assert params.sample_pin is not None

    sample_location = SampleLocation(params.sample_puck, params.sample_pin)

    yield from prepare_for_robot_load(
        composite.aperture_scatterguard, composite.smargon
    )

    yield from bpp.set_run_key_wrapper(
        bpp.run_wrapper(
            robot_load_and_snapshots(
                composite,
                sample_location,
                params.snapshot_directory,
                params.thawing_time,
                params.demand_energy_ev,
            ),
            md={
                "subplan_name": CONST.PLAN.ROBOT_LOAD,
                "metadata": {
                    "visit": params.visit,
                    "sample_id": params.sample_id,
                    "sample_puck": sample_location.puck,
                    "sample_pin": sample_location.pin,
                },
                "activate_callbacks": [
                    "RobotLoadISPyBCallback",
                ],
            },
        ),
        CONST.PLAN.ROBOT_LOAD_AND_SNAPSHOTS,
    )
