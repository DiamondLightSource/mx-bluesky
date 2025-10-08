from collections.abc import Callable
from functools import partial

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
from bluesky.preprocessors import run_decorator, subs_decorator
from bluesky.utils import MsgGenerator
from dodal.common import inject
from dodal.devices.i04.constants import RedisConstants
from dodal.devices.i04.murko_results import MurkoResultsDevice
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.oav.oav_to_redis_forwarder import OAVToRedisForwarder, Source
from dodal.devices.robot import BartRobot
from dodal.devices.smargon import Smargon
from dodal.devices.thawer import OnOff, Thawer

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


def thaw_and_stream_to_redis(
    time_to_thaw: float,
    rotation: float = 360,
    robot: BartRobot = inject("robot"),
    thawer: Thawer = inject("thawer"),
    smargon: Smargon = inject("smargon"),
    oav_fs: OAV = inject("oav_full_screen"),
    oav_roi: OAV = inject("oav_roi"),
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

    def switch_forwarder_to_ROI() -> MsgGenerator:
        yield from bps.complete(oav_to_redis_forwarder, wait=True)
        yield from bps.mv(oav_to_redis_forwarder.selected_source, Source.ROI.value)
        yield from bps.kickoff(oav_to_redis_forwarder, wait=True)

    yield from _thaw_and_stream_to_redis(
        time_to_thaw,
        rotation,
        robot,
        thawer,
        smargon,
        oav_fs,
        oav_roi,
        oav_to_redis_forwarder,
        switch_forwarder_to_ROI,
    )


def thaw_and_murko_centre(
    time_to_thaw: float,
    rotation: float = 360,
    robot: BartRobot = inject("robot"),
    thawer: Thawer = inject("thawer"),
    smargon: Smargon = inject("smargon"),
    oav_fs: OAV = inject("oav_full_screen"),
    oav_roi: OAV = inject("oav_roi"),
    murko_results: MurkoResultsDevice = inject("murko_results"),
    oav_to_redis_forwarder: OAVToRedisForwarder = inject("oav_to_redis_forwarder"),
) -> MsgGenerator:
    """Thaws the sample and centres it using murko by:
        1. Turns on the thawer
        2. Rotates the sample by {rotation} degrees, whilst this is happening images from
        the large ROI of the OAV are being fed to murko
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

    MURKO_RESULTS_GROUP = "get_results"

    def centre_then_switch_forwarder_to_ROI() -> MsgGenerator:
        yield from bps.complete(oav_to_redis_forwarder, wait=True)

        yield from bps.mv(oav_to_redis_forwarder.selected_source, Source.ROI.value)

        yield from bps.wait(MURKO_RESULTS_GROUP)
        x_predict = yield from bps.rd(murko_results.x_mm)
        y_predict = yield from bps.rd(murko_results.y_mm)
        z_predict = yield from bps.rd(murko_results.z_mm)

        yield from bps.rel_set(smargon.x, x_predict)
        yield from bps.rel_set(smargon.y, y_predict)
        yield from bps.rel_set(smargon.z, z_predict)

        yield from bps.kickoff(oav_to_redis_forwarder, wait=True)

    sample_id = yield from bps.rd(robot.sample_id)
    yield from bps.mv(murko_results.sample_id, str(sample_id))

    yield from bps.stage(murko_results, wait=True)
    yield from bps.trigger(murko_results, group=MURKO_RESULTS_GROUP)

    yield from bpp.contingency_wrapper(
        _thaw_and_stream_to_redis(
            time_to_thaw,
            rotation,
            robot,
            thawer,
            smargon,
            oav_fs,
            oav_roi,
            oav_to_redis_forwarder,
            centre_then_switch_forwarder_to_ROI,
        ),
        final_plan=partial(bps.unstage, murko_results, wait=True),
    )


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


def _thaw_and_stream_to_redis(
    time_to_thaw: float,
    rotation: float,
    robot: BartRobot,
    thawer: Thawer,
    smargon: Smargon,
    oav_fs: OAV,
    oav_roi: OAV,
    oav_to_redis_forwarder: OAVToRedisForwarder,
    plan_between_rotations: Callable[[], MsgGenerator],
) -> MsgGenerator:
    sample_id = yield from bps.rd(robot.sample_id)

    sample_id = int(sample_id)

    zoom_level_before_thawing = yield from bps.rd(oav_fs.zoom_controller.level)
    yield from bps.mv(oav_fs.zoom_controller.level, "1.0x")

    zoom_percentage_fs = yield from bps.rd(oav_fs.zoom_controller.percentage)
    microns_per_pixel_x_fs = yield from bps.rd(oav_fs.microns_per_pixel_x)
    microns_per_pixel_y_fs = yield from bps.rd(oav_fs.microns_per_pixel_y)
    beam_centre_i_fs = yield from bps.rd(oav_fs.beam_centre_i)
    beam_centre_j_fs = yield from bps.rd(oav_fs.beam_centre_j)

    zoom_percentage_roi = yield from bps.rd(oav_roi.zoom_controller.percentage)
    microns_per_pixel_x_roi = yield from bps.rd(oav_roi.microns_per_pixel_x)
    microns_per_pixel_y_roi = yield from bps.rd(oav_roi.microns_per_pixel_y)
    beam_centre_i_roi = yield from bps.rd(oav_roi.beam_centre_i)
    beam_centre_j_roi = yield from bps.rd(oav_roi.beam_centre_j)

    def _main_plan():
        inital_velocity = yield from bps.rd(smargon.omega.velocity)
        new_velocity = abs(rotation / time_to_thaw) * 2.0

        def cleanup():
            yield from bps.abs_set(smargon.omega.velocity, inital_velocity, wait=True)
            yield from bps.abs_set(thawer.control, OnOff.OFF, wait=True)

        @subs_decorator(
            MurkoCallback(
                RedisConstants.REDIS_HOST,
                RedisConstants.REDIS_PASSWORD,
                RedisConstants.MURKO_REDIS_DB,
            )
        )
        @run_decorator(
            md={
                "microns_per_x_pixel": microns_per_pixel_x_fs,
                "microns_per_y_pixel": microns_per_pixel_y_fs,
                "beam_centre_i": beam_centre_i_fs,
                "beam_centre_j": beam_centre_j_fs,
                "zoom_percentage": zoom_percentage_fs,
                "sample_id": sample_id,
            }
        )
        def thaw_part_1():
            yield from bps.mv(
                oav_to_redis_forwarder.sample_id,
                sample_id,
                oav_to_redis_forwarder.selected_source,
                Source.FULL_SCREEN.value,
            )

            yield from bps.kickoff(oav_to_redis_forwarder, wait=True)
            yield from bps.monitor(smargon.omega.user_readback, name="smargon")
            yield from bps.monitor(oav_to_redis_forwarder.uuid, name="oav")

            yield from bps.abs_set(smargon.omega.velocity, new_velocity, wait=True)
            yield from bps.abs_set(thawer.control, OnOff.ON, wait=True)
            yield from bps.rel_set(smargon.omega, rotation, wait=True)
            yield from plan_between_rotations()

            yield from bps.complete(oav_to_redis_forwarder)

        @subs_decorator(
            MurkoCallback(
                RedisConstants.REDIS_HOST,
                RedisConstants.REDIS_PASSWORD,
                RedisConstants.MURKO_REDIS_DB,
            )
        )
        @run_decorator(
            md={
                "microns_per_x_pixel": microns_per_pixel_x_roi,
                "microns_per_y_pixel": microns_per_pixel_y_roi,
                "beam_centre_i": beam_centre_i_roi,
                "beam_centre_j": beam_centre_j_roi,
                "zoom_percentage": zoom_percentage_roi,
                "sample_id": sample_id,
            }
        )
        def thaw_part_2():
            yield from bps.monitor(smargon.omega.user_readback, name="smargon")
            yield from bps.monitor(oav_to_redis_forwarder.uuid, name="oav")

            yield from bps.rel_set(smargon.omega, -rotation, wait=True)
            yield from bps.complete(oav_to_redis_forwarder)

        def do_thaw():
            yield from thaw_part_1()
            yield from thaw_part_2()

        # Always cleanup even if there is a failure
        yield from bpp.contingency_wrapper(
            do_thaw(),
            final_plan=cleanup,
        )

    def cleanup():
        yield from bps.mv(oav_fs.zoom_controller.level, zoom_level_before_thawing)

    yield from bpp.contingency_wrapper(
        _main_plan(),
        final_plan=cleanup,
    )
