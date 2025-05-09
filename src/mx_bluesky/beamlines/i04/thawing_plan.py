from collections.abc import Callable

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
from bluesky.preprocessors import run_decorator, subs_decorator
from bluesky.utils import MsgGenerator
from dodal.common import inject
from dodal.devices.i04.constants import RedisConstants
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.oav.oav_to_redis_forwarder import OAVToRedisForwarder, Source
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
    zoom_percentage = yield from bps.rd(oav.zoom_controller.percentage)
    sample_id = yield from bps.rd(robot.sample_id)

    sample_id = int(sample_id)
    zoom_level_before_thawing = yield from bps.rd(oav.zoom_controller.level)

    yield from bps.mv(oav.zoom_controller.level, "1.0x")

    def switch_forwarder_to_ROI() -> MsgGenerator:
        yield from bps.complete(oav_to_redis_forwarder, wait=True)
        yield from bps.mv(oav_to_redis_forwarder.selected_source, Source.ROI.value)
        yield from bps.kickoff(oav_to_redis_forwarder, wait=True)

    microns_per_pixel_x = yield from bps.rd(oav.microns_per_pixel_x)
    microns_per_pixel_y = yield from bps.rd(oav.microns_per_pixel_y)
    beam_centre_i = yield from bps.rd(oav.beam_centre_i)
    beam_centre_j = yield from bps.rd(oav.beam_centre_j)

    @subs_decorator(
        MurkoCallback(
            RedisConstants.REDIS_HOST,
            RedisConstants.REDIS_PASSWORD,
            RedisConstants.MURKO_REDIS_DB,
        )
    )
    @run_decorator(
        md={
            "microns_per_x_pixel": microns_per_pixel_x,
            "microns_per_y_pixel": microns_per_pixel_y,
            "beam_centre_i": beam_centre_i,
            "beam_centre_j": beam_centre_j,
            "zoom_percentage": zoom_percentage,
            "sample_id": sample_id,
        }
    )
    def _thaw_and_stream_to_redis():
        yield from bps.mv(
            oav_to_redis_forwarder.sample_id,
            sample_id,
            oav_to_redis_forwarder.selected_source,
            Source.FULL_SCREEN.value,
        )

        yield from bps.kickoff(oav_to_redis_forwarder, wait=True)
        yield from bps.monitor(smargon.omega.user_readback, name="smargon")
        yield from bps.monitor(oav_to_redis_forwarder.uuid, name="oav")
        yield from _thaw(
            time_to_thaw, rotation, thawer, smargon, switch_forwarder_to_ROI
        )
        yield from bps.complete(oav_to_redis_forwarder)

    def cleanup():
        yield from bps.mv(oav.zoom_controller.level, zoom_level_before_thawing)

    yield from bpp.contingency_wrapper(
        _thaw_and_stream_to_redis(),
        final_plan=cleanup,
    )


def thaw(
    time_to_thaw: float,
    rotation: float = 360,
    thawer: Thawer = inject("thawer"),
    smargon: Smargon = inject("smargon"),
) -> MsgGenerator:
    yield from _thaw(time_to_thaw, rotation, thawer, smargon)


def _thaw(
    time_to_thaw: float,
    rotation: float = 360,
    thawer: Thawer = inject("thawer"),
    smargon: Smargon = inject("smargon"),
    plan_between_rotations: Callable[[], MsgGenerator] | None = None,
) -> MsgGenerator:
    """Rotates the sample and thaws it at the same time.

    Args:
        time_to_thaw (float): Time to thaw for, in seconds.
        rotation (float, optional): How much to rotate by whilst thawing, in degrees.
                                    Defaults to 360.
        thawer (Thawer, optional): The thawing device. Defaults to inject("thawer").
        smargon (Smargon, optional): The smargon used to rotate.
                                     Defaults to inject("smargon")
        plan_between_rotations (MsgGenerator, optional): A plan to run between rotations
                                    of the smargon. Defaults to no plan.
    """
    inital_velocity = yield from bps.rd(smargon.omega.velocity)
    new_velocity = abs(rotation / time_to_thaw) * 2.0

    def do_thaw():
        yield from bps.abs_set(smargon.omega.velocity, new_velocity, wait=True)
        yield from bps.abs_set(thawer.control, ThawerStates.ON, wait=True)
        yield from bps.rel_set(smargon.omega, rotation, wait=True)
        if plan_between_rotations:
            yield from plan_between_rotations()
        yield from bps.rel_set(smargon.omega, -rotation, wait=True)

    def cleanup():
        yield from bps.abs_set(smargon.omega.velocity, inital_velocity, wait=True)
        yield from bps.abs_set(thawer.control, ThawerStates.OFF, wait=True)

    # Always cleanup even if there is a failure
    yield from bpp.contingency_wrapper(
        do_thaw(),
        final_plan=cleanup,
    )
