import os

import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.common import inject
from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
from dodal.devices.mx_phase1.beamstop import Beamstop, BeamstopPositions
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.robot import BartRobot, PinMounted
from dodal.devices.scintillator import InOut, Scintillator
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


# REMEMBER to add all the injects
def take_image(
    robot: BartRobot,
    beamstop: Beamstop,
    scintillator: Scintillator,
    attenuator: BinaryFilterAttenuator,
    shutter: ZebraShutter,
):
    initial_wait = "Initial wait group"
    # check pin is mounted - I think this is wrong -- recheck
    pin_mounted = yield from bps.rd(robot.gonio_pin_sensor)
    if pin_mounted == PinMounted.NO_PIN_MOUNTED:
        raise ValueError("Pin should not be mounted! ")
    # elif pin_mounted == PinMounted.PIN_MOUNTED:

    # move beamstop to data collection position
    beamstop_pos = beamstop.selected_pos
    yield from bps.abs_set(
        beamstop_pos, BeamstopPositions.DATA_COLLECTION, group=initial_wait
    )
    # beamstop.selected_pos.set(BeamstopPositions.DATA_COLLECTION)

    # move scint in
    yield from bps.abs_set(scintillator.selected_pos, InOut.IN, group=initial_wait)

    # wait
    yield from bps.wait(initial_wait)
    # set trans to 100%
    yield from bps.mv(attenuator, 1)

    # open fast shutter
    yield from bps.abs_set(shutter.control_mode, ZebraShutterControl.MANUAL, wait=True)
    yield from bps.abs_set(shutter, ZebraShutterState.OPEN, wait=True)
    # take oav image
    # image_name = "Image"
    # take_OAV_image("/workspaces/mx-bluesky/src/mx_bluesky/beamlines/i04/oav_centering_plans/images", )


def take_OAV_image(
    file_path: str,
    file_name: str,
    oav: OAV = inject("oav"),
) -> MsgGenerator:
    group = "path setting"
    yield from bps.abs_set(oav.snapshot.filename, file_name, group=group)
    yield from bps.abs_set(oav.snapshot.directory, file_path, group=group)
    yield from bps.wait(group)
    yield from bps.trigger(oav.snapshot, wait=True)


def get_available_filename(directory, base_name):
    # may need to include the extension (jpeg) as a parameter?
    counter = 1
    while True:
        filename = "f{base_name}{counter}"
        full_path = os.path.join(directory, filename)
        if not os.path.exists(full_path):
            return filename
        counter += 1
