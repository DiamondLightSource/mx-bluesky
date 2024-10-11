import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
from bluesky.preprocessors import run_decorator, subs_decorator
from dls_bluesky_core.core import MsgGenerator
from dodal.beamlines.i04 import MURKO_REDIS_DB, REDIS_HOST, REDIS_PASSWORD
from dodal.common import inject
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.oav.oav_to_redis_forwarder import OAVToRedisForwarder
from dodal.devices.robot import BartRobot
from dodal.devices.smargon import Smargon
from dodal.devices.thawer import Thawer, ThawerStates

from mx_bluesky.beamlines.i04.callbacks.murko_callback import MurkoCallback


def thaw_and_stream_to_redis(
    time_to_thaw: float,
    rotation: float = 360,
    robot: BartRobot = inject("robot"),
    thawer: Thawer = inject("thawer"),
    smargon: Smargon = inject("smargon"),
    oav: OAV = inject("oav"),
    oav_to_redis_forwarder: OAVToRedisForwarder = inject("oav_to_redis_forwarder"),
) -> MsgGenerator:
    zoom_percentage = yield from bps.rd(oav.zoom_controller.percentage)  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
    sample_id = yield from bps.rd(robot.sample_id)

    yield from bps.abs_set(oav.zoom_controller.level, "1.0x", wait=True)  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
    yield from bps.abs_set(oav_to_redis_forwarder.sample_id, sample_id)

    @subs_decorator(MurkoCallback(REDIS_HOST, REDIS_PASSWORD, MURKO_REDIS_DB))
    @run_decorator(
        md={
            "microns_per_x_pixel": oav.parameters.micronsPerXPixel,
            "microns_per_y_pixel": oav.parameters.micronsPerYPixel,
            "beam_centre_i": oav.parameters.beam_centre_i,
            "beam_centre_j": oav.parameters.beam_centre_j,
            "zoom_percentage": zoom_percentage,
            "sample_id": sample_id,
        }
    )
    def _thaw_and_stream_to_redis():
        yield from bps.kickoff(oav_to_redis_forwarder, wait=True)
        yield from bps.monitor(smargon.omega.user_readback, name="smargon")
        yield from bps.monitor(oav_to_redis_forwarder.uuid, name="oav")
        yield from thaw(time_to_thaw, rotation, thawer, smargon)
        yield from bps.complete(oav_to_redis_forwarder)

    yield from _thaw_and_stream_to_redis()


def thaw(
    time_to_thaw: float,
    rotation: float = 360,
    thawer: Thawer = inject("thawer"),
    smargon: Smargon = inject("smargon"),
) -> MsgGenerator:
    """Rotates the sample and thaws it at the same time.

    Args:
        time_to_thaw (float): Time to thaw for, in seconds.
        rotation (float, optional): How much to rotate by whilst thawing, in degrees.
                                    Defaults to 360.
        thawer (Thawer, optional): The thawing device. Defaults to inject("thawer").
        smargon (Smargon, optional): The smargon used to rotate.
                                     Defaults to inject("smargon")
    """
    inital_velocity = yield from bps.rd(smargon.omega.velocity)
    new_velocity = abs(rotation / time_to_thaw) * 2.0

    def do_thaw():
        yield from bps.abs_set(smargon.omega.velocity, new_velocity, wait=True)
        yield from bps.abs_set(thawer.control, ThawerStates.ON, wait=True)
        yield from bps.rel_set(smargon.omega, rotation, wait=True)
        yield from bps.rel_set(smargon.omega, -rotation, wait=True)

    def cleanup():
        yield from bps.abs_set(smargon.omega.velocity, inital_velocity, wait=True)
        yield from bps.abs_set(thawer.control, ThawerStates.OFF, wait=True)

    # Always cleanup even if there is a failure
    yield from bpp.contingency_wrapper(
        do_thaw(),
        final_plan=cleanup,
    )
