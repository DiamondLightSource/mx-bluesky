from collections.abc import Callable

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
from bluesky.preprocessors import run_decorator, subs_decorator
from dls_bluesky_core.core import MsgGenerator
from dodal.beamlines import i04
from dodal.beamlines.i04 import MURKO_REDIS_DB, REDIS_HOST, REDIS_PASSWORD
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.oav.oav_to_redis_forwarder import OAVToRedisForwarder, Source
from dodal.devices.robot import BartRobot
from dodal.devices.smargon import Smargon
from dodal.devices.thawer import Thawer, ThawerStates

from mx_bluesky.beamlines.i04.callbacks.murko_callback import MurkoCallback


def thaw_and_stream_to_redis(
    time_to_thaw: float,
    rotation: float = 360,
    robot: BartRobot = i04.robot(wait_for_connection=False),
    thawer: Thawer = i04.thawer(wait_for_connection=False),
    smargon: Smargon = i04.smargon(wait_for_connection=False),
    oav: OAV = i04.oav(wait_for_connection=False),
    oav_to_redis_forwarder: OAVToRedisForwarder = i04.oav_to_redis_forwarder(
        wait_for_connection=False
    ),
) -> MsgGenerator:
    zoom_percentage = yield from bps.rd(oav.zoom_controller.percentage)  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
    sample_id = yield from bps.rd(robot.sample_id)

    sample_id = int(sample_id)
    zoom_level_before_thawing = yield from bps.rd(oav.zoom_controller.level)  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809

    yield from bps.mv(oav.zoom_controller.level, "1.0x")  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809

    def switch_forwarder_to_ROI() -> MsgGenerator:
        yield from bps.complete(oav_to_redis_forwarder, wait=True)
        yield from bps.mv(oav_to_redis_forwarder.selected_source, Source.ROI)  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
        yield from bps.kickoff(oav_to_redis_forwarder, wait=True)

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
        yield from bps.mv(
            oav_to_redis_forwarder.sample_id,  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
            sample_id,  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
            oav_to_redis_forwarder.selected_source,  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
            Source.FULL_SCREEN,  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
        )

        yield from bps.kickoff(oav_to_redis_forwarder, wait=True)
        yield from bps.monitor(smargon.omega.user_readback, name="smargon")
        yield from bps.monitor(oav_to_redis_forwarder.uuid, name="oav")
        yield from thaw(
            time_to_thaw, rotation, thawer, smargon, switch_forwarder_to_ROI
        )
        yield from bps.complete(oav_to_redis_forwarder)

    def cleanup():
        yield from bps.mv(oav.zoom_controller.level, zoom_level_before_thawing)  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809

    yield from bpp.contingency_wrapper(
        _thaw_and_stream_to_redis(),
        final_plan=cleanup,
    )


def thaw(
    time_to_thaw: float,
    rotation: float = 360,
    thawer: Thawer = i04.thawer(wait_for_connection=False),
    smargon: Smargon = i04.smargon(wait_for_connection=False),
    plan_between_rotations: Callable[[], MsgGenerator] | None = None,
) -> MsgGenerator:
    """Rotates the sample and thaws it at the same time.

    Args:
        time_to_thaw (float): Time to thaw for, in seconds.
        rotation (float, optional): How much to rotate by whilst thawing, in degrees.
                                    Defaults to 360.
        thawer (Thawer, optional): The thawing device. Defaults to i04.thawer(wait_for_connection=False).
        smargon (Smargon, optional): The smargon used to rotate.
                                     Defaults to i04.smargon(wait_for_connection=False)
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
