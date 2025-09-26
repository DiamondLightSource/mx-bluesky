# import bluesky.plan_stubs as bps
# from bluesky.utils import MsgGenerator
# from dodal.common import inject
# from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
# from dodal.devices.oav.oav_detector import OAV
# from dodal.devices.scintillator import InOut, Scintillator
# from dodal.devices.xbpm_feedback import XBPMFeedback
# from dodal.devices.zebra.zebra_controlled_shutter import (
#     ZebraShutter,
#     ZebraShutterControl,
#     ZebraShutterState,
# )


"""
Check with the robot that there is no pin mounted. If there is raise an exception with a nice error message.
Move the beamstop to data collection position
Move the scintillator in (will need
Add ability to move scintillator into beam dodal#1567)
Wait for the above to finish
Set transmission to 100%
Open the fast shutter
Take an OAV image
"""
