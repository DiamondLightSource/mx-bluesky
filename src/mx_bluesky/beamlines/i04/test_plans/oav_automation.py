import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.common import inject
from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.scintillator import InOut, Scintillator
from dodal.devices.xbpm_feedback import XBPMFeedback
from dodal.devices.zebra.zebra_controlled_shutter import (
    ZebraShutter,
    ZebraShutterControl,
    ZebraShutterState,
)

# from dodal.devices.oav.snapshots.snapshot_with_grid import SnapshotWithGrid

"""
My task:
    Move the scintillator in and out
    Change transmission percentage
    Take OAV images
    Open and close fast shutter
"""


# def oav_automation_test()
def feedback_check(
    device: XBPMFeedback = inject("xbpm_feedback"),
):
    yield from bps.trigger(device)


def set_transmission_percentage(
    percentage: float,
    attenuator: BinaryFilterAttenuator = inject("attenuator"),
) -> MsgGenerator:
    yield from bps.abs_set(attenuator, percentage / 100)


def open_close_fast_shutter(
    shutter_state: ZebraShutterState,
    shutter: ZebraShutter = inject("fast_shutter"),
) -> MsgGenerator:
    base_control_mode = yield from bps.rd(shutter.control_mode)

    yield from bps.abs_set(shutter.control_mode, ZebraShutterControl.MANUAL)
    yield from bps.abs_set(shutter, shutter_state)

    yield from bps.abs_set(shutter.control_mode, base_control_mode)


def take_OAV_image(
    file_path: str,
    file_name: str,
    oav: OAV = inject("oav"),
) -> MsgGenerator:
    group = "path setting"
    yield from bps.abs_set(oav.grid_snapshot.filename, file_name, group=group)
    yield from bps.abs_set(oav.grid_snapshot.directory, file_path, group=group)
    yield from bps.wait(group)
    yield from bps.trigger(oav.grid_snapshot)


def move_scintillator(
    scintillator_state: InOut, scintillator: Scintillator = inject("scintillator")
) -> MsgGenerator:
    yield from bps.abs_set(scintillator.selected_pos, scintillator_state)
