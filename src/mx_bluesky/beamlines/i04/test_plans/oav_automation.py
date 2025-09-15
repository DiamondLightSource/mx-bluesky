
from bluesky.utils import MsgGenerator
import bluesky.plan_stubs as bps
#import bluesky.preprocessors as bpp
#from bluesky.preprocessors import run_decorator, stage_wrapper, subs_decorator
from bluesky.utils import MsgGenerator

from dodal.common import inject
from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
from dodal.devices.zebra.zebra_controlled_shutter import ZebraShutter, ZebraShutterState, ZebraShutterControl
from sqlalchemy import Boolean

"""
My task: 

    Move the scintillator in and out
    Change transmission percentage
    Take OAV images
    Open and close fast shutter

"""


def set_transmission_percentage(
    percentage: float,
    attenuator: BinaryFilterAttenuator,
) -> MsgGenerator:

    yield from bps.abs_set(attenuator, percentage/100)


def open_close_fast_shutter(
        shutter: ZebraShutter, 
        shutter_state: Boolean, 
        #shutter_control: ZebraShutterControl

) -> MsgGenerator:
    
    yield from bps.abs_set(shutter.control_mode, ZebraShutterControl.MANUAL)
    if shutter_state:
        yield from bps.abs_set(shutter._manual_position_setpoint, ZebraShutterState.OPEN)
    else: 
        yield from bps.abs_set(shutter._manual_position_setpoint, ZebraShutterState.CLOSE)

def move_scintillator():
    pass

def take_OAV_image():
    pass 


