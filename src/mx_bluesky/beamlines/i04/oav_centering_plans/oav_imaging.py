import time

import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.common import inject
from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
from dodal.devices.backlight import Backlight
from dodal.devices.mx_phase1.beamstop import Beamstop, BeamstopPositions
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.robot import BartRobot, PinMounted
from dodal.devices.scintillator import InOut, Scintillator
from dodal.devices.xbpm_feedback import XBPMFeedback
from dodal.devices.zebra.zebra_controlled_shutter import (
    ZebraShutter,
    ZebraShutterControl,
    ZebraShutterState,
)
from ophyd_async.core import InOut as core_INOUT

from mx_bluesky.common.utils.exceptions import BeamlineStateException

group = "path setting"


def take_oav_image_with_scintillator_in(
    image_name: str | None = None,
    image_path: str = "dls_sw/i04/software/bluesky/scratch",
    transmission: float = 1,
    attenuator: BinaryFilterAttenuator = inject("attenuator"),
    shutter: ZebraShutter = inject("sample_shutter"),
    oav: OAV = inject("oav"),
) -> MsgGenerator:
    """
    Takes an OAV image at specified transmission after necessary checks and preparation steps.

    Args:
        image_name: Name of the OAV image to be saved
        image_path: Path where the image should be saved
        transmission: Set the transmission of the beam, takes a value from 0 to 1 where
        1 lets all the beam through and 0 lets none of the beam through.
        devices: These are the specific ophyd-devices used for the plan, the
                     defaults are always correct.
    """
    initial_wait = "Wait for scint to move in"

    _prepare_beamline_for_scintillator_images(initial_wait=initial_wait)

    yield from bps.abs_set(attenuator, transmission, group=initial_wait)

    if image_name is None:
        image_name = f"{time.time_ns()}ATT{transmission * 100}"

    yield from bps.wait(initial_wait)

    yield from bps.abs_set(shutter.control_mode, ZebraShutterControl.MANUAL, wait=True)
    yield from bps.abs_set(shutter, ZebraShutterState.OPEN, wait=True)

    take_and_save_oav_image(file_path=image_path, file_name=image_name, oav=oav)


def _prepare_beamline_for_scintillator_images(
    initial_wait: str,
    robot: BartRobot = inject("robot"),
    beamstop: Beamstop = inject("beamstop"),
    backlight: Backlight = inject("backlight"),
    scintillator: Scintillator = inject("scintillator"),
    xbpm_feedback: XBPMFeedback = inject("xbpm_feedback"),
) -> MsgGenerator:
    """
    Prepares the beamline for oav image by making sure the pin is NOT mounted and
    the beam is on (feedback check). Finally, the scintillator is moved in.
    """
    pin_mounted = yield from bps.rd(robot.gonio_pin_sensor)
    if pin_mounted == PinMounted.PIN_MOUNTED:
        raise BeamlineStateException("Pin should not be mounted!")

    yield from bps.trigger(xbpm_feedback, wait=True)

    beamstop_pos = beamstop.selected_pos
    yield from bps.abs_set(
        beamstop_pos, BeamstopPositions.DATA_COLLECTION, group=initial_wait
    )

    yield from bps.abs_set(backlight, core_INOUT.OUT, group=initial_wait)

    yield from bps.abs_set(scintillator.selected_pos, InOut.IN, group=initial_wait)


def take_and_save_oav_image(
    file_name: str,
    file_path: str,
    oav: OAV,
) -> MsgGenerator:
    """
    Plan which takes and saves an OAV image to the specified path.
     Args:
        file_name: Filename specifying the name of the image,
        file_path: Path as a string specifying where the image should be saved,
        devices: These are the specific ophyd-devices used for the plan, the
                     defaults are always correct.
    """
    yield from bps.abs_set(oav.snapshot.filename, file_name, group=group)
    yield from bps.abs_set(oav.snapshot.directory, file_path, group=group)
    yield from bps.wait(group)
    yield from bps.trigger(oav.snapshot, wait=True)
