from datetime import datetime
from typing import Protocol

from bluesky import plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.devices.aperturescatterguard import ApertureScatterguard, ApertureValue
from dodal.devices.backlight import Backlight, BacklightPosition
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.oav.oav_parameters import OAVParameters
from dodal.devices.smargon import Smargon

from mx_bluesky.common.parameters.components import WithSnapshot
from mx_bluesky.hyperion.device_setup_plans.setup_oav import setup_general_oav_params
from mx_bluesky.hyperion.parameters.constants import CONST, DocDescriptorNames

OAV_SNAPSHOT_SETUP_SHOT = "oav_snapshot_setup_shot"
OAV_SNAPSHOT_GROUP = "oav_snapshot_group"


class OavSnapshotComposite(Protocol):
    smargon: Smargon
    oav: OAV
    aperture_scatterguard: ApertureScatterguard
    backlight: Backlight


def setup_beamline_for_OAV(
    smargon: Smargon,
    backlight: Backlight,
    aperture_scatterguard: ApertureScatterguard,
    group=CONST.WAIT.READY_FOR_OAV,
):
    max_vel = yield from bps.rd(smargon.omega.max_velocity)
    yield from bps.abs_set(smargon.omega.velocity, max_vel, group=group)
    yield from bps.abs_set(backlight, BacklightPosition.IN, group=group)
    yield from bps.abs_set(
        aperture_scatterguard,
        ApertureValue.ROBOT_LOAD,
        group=group,
    )


def oav_snapshot_plan(
    composite: OavSnapshotComposite,
    parameters: WithSnapshot,
    oav_parameters: OAVParameters,
    wait: bool = True,
) -> MsgGenerator:
    if not parameters.take_snapshots:
        return
    yield from bps.wait(group=CONST.WAIT.READY_FOR_OAV)
    yield from _setup_oav(composite, parameters, oav_parameters)
    for omega in parameters.snapshot_omegas_deg or []:
        yield from _take_oav_snapshot(composite, omega)


def _setup_oav(
    composite: OavSnapshotComposite,
    parameters: WithSnapshot,
    oav_parameters: OAVParameters,
):
    yield from setup_general_oav_params(composite.oav, oav_parameters)
    yield from bps.abs_set(
        composite.oav.snapshot.directory,  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
        str(parameters.snapshot_directory),
    )


def _take_oav_snapshot(composite: OavSnapshotComposite, omega: float):
    yield from bps.abs_set(
        composite.smargon.omega, omega, group=OAV_SNAPSHOT_SETUP_SHOT
    )
    time_now = datetime.now()
    filename = f"{time_now.strftime('%H%M%S')}_oav_snapshot_{omega:.0f}"
    yield from bps.abs_set(
        composite.oav.snapshot.filename,  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
        filename,
        group=OAV_SNAPSHOT_SETUP_SHOT,
    )
    yield from bps.wait(group=OAV_SNAPSHOT_SETUP_SHOT)
    yield from bps.trigger(composite.oav.snapshot, wait=True)  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
    yield from bps.create(DocDescriptorNames.OAV_ROTATION_SNAPSHOT_TRIGGERED)
    yield from bps.read(composite.oav.snapshot)  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
    yield from bps.save()
