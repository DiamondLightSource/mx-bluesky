from __future__ import annotations

from functools import partial

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
from dodal.devices.hutch_shutter import ShutterState
from dodal.devices.i24.aperture import AperturePositions
from dodal.devices.i24.beamstop import BeamstopPositions
from dodal.devices.i24.dual_backlight import BacklightPositions
from dodal.devices.zebra.zebra import Zebra
from dodal.plan_stubs.check_topup import check_topup_and_wait_if_necessary
from ophyd_async.fastcs.jungfrau import (
    create_jungfrau_external_triggering_info,
)

from mx_bluesky.beamlines.i24.jungfrau_commissioning.callbacks.metadata_writer import (
    JsonMetadataWriter,
)
from mx_bluesky.beamlines.i24.jungfrau_commissioning.composites import (
    RotationScanComposite,
)
from mx_bluesky.beamlines.i24.jungfrau_commissioning.plan_utils import (
    JF_COMPLETE_GROUP,
    fly_jungfrau,
    override_file_name_and_path,
)
from mx_bluesky.beamlines.i24.jungfrau_commissioning.utility_plans import (
    read_devices_for_metadata,
)
from mx_bluesky.beamlines.i24.serial.setup_beamline.setup_zebra_plans import (
    disarm_zebra,
)
from mx_bluesky.common.experiment_plans.rotation.rotation_utils import (
    RotationMotionProfile,
    calculate_motion_profile,
)
from mx_bluesky.common.experiment_plans.setup_zebra import (
    arm_zebra,
    setup_zebra_for_rotation,
)
from mx_bluesky.common.parameters.constants import (
    PlanGroupCheckpointConstants,
    PlanNameConstants,
)
from mx_bluesky.common.parameters.rotation import (
    SingleRotationScan,
)
from mx_bluesky.common.utils.log import LOGGER

EXPERIMENT_PARAM_DUMP_FILENAME = "experiment_params.json"
READING_DUMP_FILENAME = "collection_info.json"

JF_DET_STAGE_Y_POSITION = 730


def set_up_beamline_for_rotation(composite: RotationScanComposite, det_z_mm: float):
    """Check hutch is open, move backlight in, then, in parallel,
    move aperture in, move backlight out and move det stage in"""

    hutch_shutter_state: ShutterState = yield from bps.rd(
        composite.hutch_shutter.status
    )
    LOGGER.info(f"Hutch shutter: {hutch_shutter_state}")
    if hutch_shutter_state != ShutterState.OPEN:
        LOGGER.error(f"Hutch shutter is not open! State is {hutch_shutter_state}")
        raise Exception(f"Hutch shutter is not open! State is {hutch_shutter_state}")
    LOGGER.info("Making sure backlight is moved out...")
    yield from bps.mv(composite.backlight.backlight_position, BacklightPositions.OUT)

    LOGGER.info(
        "Making sure aperture and beamstop are in, detector stage is in position, and detector distance is correct."
    )
    yield from bps.mv(
        composite.aperture.position,
        AperturePositions.IN,
        composite.beamstop.pos_select,
        BeamstopPositions.DATA_COLLECTION,
        composite.det_stage.y,
        JF_DET_STAGE_Y_POSITION,
        composite.det_stage.z,
    )


def single_rotation_plan(
    composite: RotationScanComposite,
    params: SingleRotationScan,
):
    """Set-up beamline for rotation by moving out backlight, then moving aperture, beamstop and detetor stages into position.
    Then rotate around the omega axis, capturing images at the specified omega interval.

    Args:
    composite: Composite for all devices required for this plan
    params: Minimum set of parameters required for this plan
    """

    # This should be somewhere more sensible - like in the parameter model
    if not params.detector_distance_mm:
        raise ValueError("Must specify detector distance in mm")

    yield from set_up_beamline_for_rotation(composite, params.detector_distance_mm)
    beam_xy = params.detector_params.get_beam_position_mm(params.detector_distance_mm)
    LOGGER.info(
        f"Moving detector Z stage to specified {params.detector_distance_mm} mm..."
    )
    # This can probably be done in parallel with other stuff, but will do wait for now until tested
    yield from bps.mv(composite.det_stage.z, params.detector_distance_mm)

    # This value isn't actually used, see https://github.com/DiamondLightSource/mx-bluesky/issues/1224
    _motor_time_to_speed = 1
    _max_velocity_deg_s = yield from bps.rd(composite.gonio.omega.max_velocity)

    motion_values = calculate_motion_profile(
        params, _motor_time_to_speed, _max_velocity_deg_s
    )

    metadata_writer = JsonMetadataWriter(beam_xy)

    @bpp.subs_decorator([metadata_writer])
    @bpp.set_run_key_decorator(PlanNameConstants.ROTATION_MAIN)
    @bpp.run_decorator(
        md={
            "subplan_name": PlanNameConstants.ROTATION_MAIN,
            "scan_points": [params.scan_points],
            "rotation_scan_params": params.model_dump_json(),
        }
    )
    def _rotation_scan_plan(
        motion_values: RotationMotionProfile,
        composite: RotationScanComposite,
    ):
        # Use smallest safe deadtime and neglect from motion calcualtions
        _deadtime = 2e-5

        _jf_trigger_info = create_jungfrau_external_triggering_info(
            params.num_images, params.detector_params.exposure_time_s, _deadtime
        )

        axis = composite.gonio.omega

        # can move to start as fast as possible
        yield from bps.abs_set(
            axis.velocity, motion_values.max_velocity_deg_s, wait=True
        )
        LOGGER.info(f"Moving omega to beginning, {motion_values.start_scan_deg=}")
        yield from bps.abs_set(
            axis,
            motion_values.start_motion_deg,
            group=PlanGroupCheckpointConstants.ROTATION_READY_FOR_DC,
        )

        yield from setup_zebra_for_rotation(
            composite.zebra,
            composite.sample_shutter,
            start_angle=motion_values.start_scan_deg,
            scan_width=motion_values.scan_width_deg,
            direction=motion_values.direction,
            shutter_opening_deg=motion_values.shutter_opening_deg,
            shutter_opening_s=motion_values.shutter_time_s,
            group=PlanGroupCheckpointConstants.SETUP_ZEBRA_FOR_ROTATION,
        )

        LOGGER.info("Wait for any previous moves...")
        # wait for all the setup tasks at once
        yield from bps.wait(PlanGroupCheckpointConstants.ROTATION_READY_FOR_DC)
        yield from bps.wait(PlanGroupCheckpointConstants.MOVE_GONIO_TO_START)

        # Get ready for the actual scan
        yield from bps.abs_set(
            axis.velocity, motion_values.speed_for_rotation_deg_s, wait=True
        )

        yield from bps.wait(PlanGroupCheckpointConstants.SETUP_ZEBRA_FOR_ROTATION)
        yield from arm_zebra(composite.zebra)

        # Check topup gate
        yield from check_topup_and_wait_if_necessary(
            composite.synchrotron,
            motion_values.total_exposure_s,
            ops_time=10.0,  # Additional time to account for rotation, is s
        )  # See #https://github.com/DiamondLightSource/hyperion/issues/932

        # override_file_name_and_path(
        #     composite.jungfrau,
        #     f"{params.storage_directory}/{params.detector_params.full_filename}",
        # )

        yield from read_devices_for_metadata(composite)

        yield from fly_jungfrau(
            composite.jungfrau,
            _jf_trigger_info,
            wait=False,
            log_on_percentage_message="Jungfrau rotation scan triggers received",
        )

        LOGGER.info("Executing rotation scan")
        yield from bps.rel_set(axis, motion_values.distance_to_move_deg, wait=True)

        yield from bps.wait(group=JF_COMPLETE_GROUP)

    # TODO check bluesky doesnt already do this for us
    yield from bpp.contingency_wrapper(
        _rotation_scan_plan(motion_values, composite),
        except_plan=lambda _: (yield from bps.unstage(composite.jungfrau)),
    )

    yield from bpp.finalize_wrapper(
        _rotation_scan_plan(motion_values, composite),
        final_plan=partial(_cleanup_plan, composite.zebra),
    )


def _cleanup_plan(zebra: Zebra, group="cleanup"):
    LOGGER.info("Tidying up zebra...")
    yield from bps.abs_set(zebra.inputs.soft_in_1, 0, group=group)
    yield from disarm_zebra(zebra)
    yield from bps.wait("cleanup")
