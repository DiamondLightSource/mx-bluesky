import time

import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.common import inject
from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
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

"""
Check with the robot that there is no pin mounted. If there is raise an exception with a nice error message.
Move the beamstop to data collection position
Move the scintillator in
Wait for the above to finish
Set transmission to 100%
Open the fast shutter
Take an OAV image
"""


# need to make sure you return the MsgGenerator type and read up on this
def take_image(
    image_name: str = f"{time.time_ns()}",
    # check if there is a default path we can use
    image_path: str = "/dls/mx-scratch/OAV_Images",
    robot: BartRobot = inject("robot"),
    beamstop: Beamstop = inject("beamstop"),
    scintillator: Scintillator = inject("scintillator"),
    attenuator: BinaryFilterAttenuator = inject("attenuator"),
    shutter: ZebraShutter = inject("sample_shutter"),
    oav: OAV = inject("oav"),
    feedback: XBPMFeedback = inject("xbpm_feedback"),
) -> MsgGenerator:
    initial_wait = "Wait for scint to move in"
    # check pin is mounted
    pin_mounted = yield from bps.rd(robot.gonio_pin_sensor)
    if pin_mounted == PinMounted.NO_PIN_MOUNTED:
        raise ValueError("Pin should not be mounted!")

    # feedback check
    yield from bps.trigger(feedback, wait=True)

    # move beamstop to data collection position
    beamstop_pos = beamstop.selected_pos
    yield from bps.abs_set(
        beamstop_pos, BeamstopPositions.DATA_COLLECTION, group=initial_wait
    )

    # move scint in
    yield from bps.abs_set(scintillator.selected_pos, InOut.IN, group=initial_wait)

    # set trans to 100%
    yield from bps.abs_set(attenuator, 1, group=initial_wait)

    # wait
    yield from bps.wait(initial_wait)

    # open fast shutter
    yield from bps.abs_set(shutter.control_mode, ZebraShutterControl.MANUAL, wait=True)
    yield from bps.abs_set(shutter, ZebraShutterState.OPEN, wait=True)

    # take image
    take_OAV_image(file_path=image_path, file_name=image_name, oav=oav)


def take_OAV_image(
    file_path: str,
    file_name: str,
    oav: OAV,
) -> MsgGenerator:
    group = "path setting"
    yield from bps.abs_set(oav.snapshot.filename, file_name, group=group)
    yield from bps.abs_set(oav.snapshot.directory, file_path, group=group)
    yield from bps.wait(group)
    yield from bps.trigger(oav.snapshot, wait=True)
