from collections.abc import Callable

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
from bluesky.preprocessors import (
    run_decorator,
    subs_decorator,
)
from bluesky.utils import MsgGenerator
from dodal.common import inject
from dodal.devices.i04.constants import RedisConstants
from dodal.devices.i04.murko_results import MurkoResultsDevice
from dodal.devices.oav.oav_to_redis_forwarder import OAVToRedisForwarder, Source
from dodal.devices.robot import BartRobot
from dodal.devices.smargon import Smargon
from dodal.devices.thawer import OnOff, Thawer
from dodal.log import LOGGER

from mx_bluesky.beamlines.i04.callbacks.murko_callback import MurkoCallback


def thaw(
    time_to_thaw: float,
    rotation: float = 360,
    thawer: Thawer = inject("thawer"),
    smargon: Smargon = inject("smargon"),
) -> MsgGenerator:
    """Turns on the thawer and rotates the sample by {rotation} degrees to thaw it, then
    rotates {rotation} degrees back and turns the thawer off. The speed of the goniometer
    is set such that the process takes whole process will take {time_to_thaw} time.

    Args:
        time_to_thaw (float): Time to thaw for, in seconds.
        rotation (float, optional): How much to rotate by whilst thawing, in degrees.
                                    Defaults to 360.
        ... devices: These are the specific ophyd-devices used for the plan, the
                     defaults are always correct.
    """
    yield from _thaw(time_to_thaw, rotation, thawer, smargon)


def _thaw(
    time_to_thaw: float,
    rotation: float,
    thawer: Thawer,
    smargon: Smargon,
    plan_between_rotations: Callable[[], MsgGenerator] | None = None,
) -> MsgGenerator:
    """Turns on the thawer and rotates the sample by {rotation} degrees to thaw it, then
    rotates {rotation} degrees back and turns the thawer off. The speed of the goniometer
    is set such that the process takes whole process will take {time_to_thaw} time.

    At the same time streams OAV images to redis for later processing (e.g. by murko).
    On the first rotation the images from the large ROI are streamed, on the second the
    smaller ROI is used.

    Args:
        time_to_thaw (float): Time to thaw for, in seconds.
        rotation (float): How much to rotate by whilst thawing, in degrees.
        thawer (Thawer): The thawing device.
        smargon (Smargon): The smargon used to rotate.
        plan_between_rotations (MsgGenerator, optional): A plan to run between rotations
                                    of the smargon. Defaults to no plan.
    """
    inital_velocity = yield from bps.rd(smargon.omega.velocity)
    new_velocity = abs(rotation / time_to_thaw) * 2.0

    def do_thaw():
        yield from bps.abs_set(smargon.omega.velocity, new_velocity, wait=True)
        yield from bps.abs_set(thawer.control, OnOff.ON, wait=True)
        yield from bps.rel_set(smargon.omega, rotation, wait=True)
        if plan_between_rotations:
            yield from plan_between_rotations()
        yield from bps.rel_set(smargon.omega, -rotation, wait=True)

    def cleanup():
        yield from bps.abs_set(smargon.omega.velocity, inital_velocity, wait=True)
        yield from bps.abs_set(thawer.control, OnOff.OFF, wait=True)

    # Always cleanup even if there is a failure
    yield from bpp.contingency_wrapper(
        do_thaw(),
        final_plan=cleanup,
    )


MURKO_RESULTS_GROUP = "get_results"


def thaw_and_murko_centre(
    time_to_thaw: float,
    rotation: float = 360,
    robot: BartRobot = inject("robot"),
    thawer: Thawer = inject("thawer"),
    smargon: Smargon = inject("smargon"),
    murko_results: MurkoResultsDevice = inject("murko_results"),
    oav_to_redis_forwarder: OAVToRedisForwarder = inject("oav_to_redis_forwarder"),
) -> MsgGenerator:
    """Thaws the sample and centres it using murko by:
        1. Turns on the thawer
        2. Rotates the sample by {rotation} degrees, whilst this is happening images from
        the full screen OAV are being fed to murko
        3. After the rotation has completed moves to the average centre returned by murko
        from these images
        4. Rotate {rotation} degrees back to the start, whilst this is happening images
        from the small ROI of the OAV are being fed to murko
        5. Turns off the thawer

    The speed of the goniometer is set so that all of the above takes about {time_to_thaw}
    seconds to complete.

    Args:
        time_to_thaw (float): Time to thaw for, in seconds.
        rotation (float, optional): How much to rotate by whilst thawing, in degrees.
                                    Defaults to 360.
        ... devices: These are the specific ophyd-devices used for the plan, the
                     defaults are always correct
    """

    sample_id = yield from bps.rd(robot.sample_id)
    sample_id = int(sample_id)

    oav_fs = oav_to_redis_forwarder.sources[Source.FULL_SCREEN].oav_ref()

    initial_zoom_level = yield from bps.rd(oav_fs.zoom_controller.level)
    initial_velocity = yield from bps.rd(smargon.omega.velocity)
    new_velocity = abs(rotation / time_to_thaw) * 2.0

    def cleanup():
        yield from bps.mv(oav_fs.zoom_controller.level, initial_zoom_level)
        yield from bps.abs_set(smargon.omega.velocity, initial_velocity, wait=True)
        yield from bps.abs_set(thawer.control, OnOff.OFF, wait=True)

    def centre_from_murko():
        yield from bps.complete(oav_to_redis_forwarder, wait=True)
        yield from bps.wait(MURKO_RESULTS_GROUP)

        x_predict = yield from bps.rd(murko_results.x_mm)
        y_predict = yield from bps.rd(murko_results.y_mm)
        z_predict = yield from bps.rd(murko_results.z_mm)

        LOGGER.info(f"Got results: {x_predict, y_predict, z_predict}")

        yield from bps.rel_set(smargon.x, x_predict)
        yield from bps.rel_set(smargon.y, y_predict)
        yield from bps.rel_set(smargon.z, z_predict)

    def do_thaw_and_murko_centre():
        yield from bps.mv(murko_results.sample_id, str(sample_id))
        yield from bps.mv(oav_fs.zoom_controller.level, "1.0x")
        yield from bps.abs_set(smargon.omega.velocity, new_velocity, wait=True)
        yield from bps.abs_set(thawer.control, OnOff.ON, wait=True)

        @subs_decorator(
            MurkoCallback(
                RedisConstants.REDIS_HOST,
                RedisConstants.REDIS_PASSWORD,
                RedisConstants.MURKO_REDIS_DB,
            )
        )
        @run_decorator(md={"sample_id": sample_id})
        def rotate_in_one_direction_then_murko_centre(
            rotation: float, stop_angle: float, source: Source
        ):
            inverted = rotation < 0
            yield from bps.mv(
                murko_results.stop_angle,
                stop_angle,
                murko_results.invert_stop_angle,
                inverted,
            )

            yield from bps.stage(murko_results, wait=True)
            yield from bps.trigger(murko_results, group=MURKO_RESULTS_GROUP)

            yield from _rotate_in_one_direction_and_stream_to_redis(
                smargon, oav_to_redis_forwarder, source, sample_id, rotation
            )

            yield from centre_from_murko()
            yield from bps.unstage(murko_results, wait=True)

        yield from rotate_in_one_direction_then_murko_centre(
            rotation, 350, Source.FULL_SCREEN
        )
        yield from rotate_in_one_direction_then_murko_centre(-rotation, 10, Source.ROI)

    yield from bpp.contingency_wrapper(
        do_thaw_and_murko_centre(),
        final_plan=cleanup,
    )


def thaw_and_stream_to_redis(
    time_to_thaw: float,
    rotation: float = 360,
    robot: BartRobot = inject("robot"),
    thawer: Thawer = inject("thawer"),
    smargon: Smargon = inject("smargon"),
    oav_to_redis_forwarder: OAVToRedisForwarder = inject("oav_to_redis_forwarder"),
) -> MsgGenerator:
    """Turns on the thawer and rotates the sample by {rotation} degrees to thaw it, then
    rotates {rotation} degrees back and turns the thawer off. The speed of the goniometer
    is set such that the process takes whole process will take {time_to_thaw} time.

    At the same time streams OAV images to redis for later processing (e.g. by murko).
    On the first rotation the images from the large ROI are streamed, on the second the
    smaller ROI is used.

    Args:
        time_to_thaw (float): Time to thaw for, in seconds.
        rotation (float, optional): How much to rotate by whilst thawing, in degrees.
                                    Defaults to 360.
        ... devices: These are the specific ophyd-devices used for the plan, the
                     defaults are always correct
    """
    sample_id = yield from bps.rd(robot.sample_id)
    sample_id = int(sample_id)

    oav_fs = oav_to_redis_forwarder.sources[Source.FULL_SCREEN].oav_ref()

    initial_zoom_level = yield from bps.rd(oav_fs.zoom_controller.level)
    initial_velocity = yield from bps.rd(smargon.omega.velocity)
    new_velocity = abs(rotation / time_to_thaw) * 2.0

    def cleanup():
        yield from bps.mv(oav_fs.zoom_controller.level, initial_zoom_level)
        yield from bps.abs_set(smargon.omega.velocity, initial_velocity, wait=True)
        yield from bps.abs_set(thawer.control, OnOff.OFF, wait=True)

    def do_thaw_and_stream_to_redis():
        yield from bps.mv(oav_fs.zoom_controller.level, "1.0x")
        yield from bps.abs_set(smargon.omega.velocity, new_velocity, wait=True)
        yield from bps.abs_set(thawer.control, OnOff.ON, wait=True)

        @subs_decorator(
            MurkoCallback(
                RedisConstants.REDIS_HOST,
                RedisConstants.REDIS_PASSWORD,
                RedisConstants.MURKO_REDIS_DB,
            )
        )
        @run_decorator(md={"sample_id": sample_id})
        def rotate_in_one_direction_and_stream_to_redis(
            rotation: float, source: Source
        ):
            yield from _rotate_in_one_direction_and_stream_to_redis(
                smargon, oav_to_redis_forwarder, source, sample_id, rotation
            )

        yield from rotate_in_one_direction_and_stream_to_redis(
            rotation, Source.FULL_SCREEN
        )
        yield from rotate_in_one_direction_and_stream_to_redis(-rotation, Source.ROI)

    yield from bpp.contingency_wrapper(
        do_thaw_and_stream_to_redis(),
        final_plan=cleanup,
    )


def _rotate_in_one_direction_and_stream_to_redis(
    smargon: Smargon,
    oav_to_redis_forwarder: OAVToRedisForwarder,
    source: Source,
    sample_id: int,
    rotation: float,
):
    def get_metadata_from_current_oav():
        current_source_idx = yield from bps.rd(oav_to_redis_forwarder.selected_source)
        oav = oav_to_redis_forwarder.sources[current_source_idx].oav_ref()
        yield from bps.create()
        oav_info = yield from bps.read(oav)
        LOGGER.info(f"Got oav information: {oav_info}")
        yield from bps.save()

    yield from get_metadata_from_current_oav()
    yield from bps.monitor(smargon.omega.user_readback, name="smargon")
    yield from bps.monitor(oav_to_redis_forwarder.uuid, name="oav")

    yield from bps.mv(
        oav_to_redis_forwarder.sample_id,
        sample_id,
        oav_to_redis_forwarder.selected_source,
        source.value,
    )

    yield from bps.kickoff(oav_to_redis_forwarder, wait=True)
    yield from bps.rel_set(smargon.omega, rotation, wait=True)
