
from bluesky.utils import MsgGenerator
import bluesky.plan_stubs as bps
#import bluesky.preprocessors as bpp
#from bluesky.preprocessors import run_decorator, stage_wrapper, subs_decorator
from bluesky.utils import MsgGenerator

from dodal.common import inject
from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator

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

  
def move_scintillator():
    pass

def take_OAV_image():
    pass 

def open_close_fast_shutter():
    pass
