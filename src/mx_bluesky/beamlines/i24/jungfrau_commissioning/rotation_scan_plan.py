from __future__ import annotations

from copy import deepcopy
from functools import partial
from ophyd_async.fastcs.jungfrau import GainMode
import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
from bluesky.preprocessors import run_decorator
from dodal.devices.hutch_shutter import ShutterState
from dodal.devices.i24.aperture import AperturePositions
from dodal.devices.i24.beamstop import BeamstopPositions
from dodal.devices.i24.commissioning_jungfrau import CommissioningJungfrau
from dodal.devices.i24.dual_backlight import BacklightPositions
from dodal.devices.zebra.zebra import I24Axes, Zebra
from dodal.devices.zebra.zebra_controlled_shutter import ZebraShutter
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
    override_file_path,
)
from mx_bluesky.beamlines.i24.jungfrau_commissioning.utility_plans import (
    read_devices_for_metadata,
)
from mx_bluesky.beamlines.i24.parameters.constants import (
    PlanNameConstants as I24PlanNameConstants,
)
from mx_bluesky.beamlines.i24.parameters.rotation import (
    MultiRotationScanByTransmissions,
)
from mx_bluesky.common.device_setup_plans.setup_zebra_and_shutter import (
    tidy_up_zebra_after_rotation_scan,
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

READING_DUMP_FILENAME = "collection_info.json"
JF_DET_STAGE_Y_POSITION_MM = 730
DEFAULT_DETECTOR_DISTANCE_MM = 200


def set_up_beamline_for_rotation(
    composite: RotationScanComposite,
    det_z_mm: float,
    transmission_frac: float,
):
    """Check hutch is open, then, in parallel, move backlight in,
    move aperture in, move backlight out and move det stages in. Wait for this parallel
    move to finish."""

    hutch_shutter_state: ShutterState = yield from bps.rd(
        composite.hutch_shutter.status
    )
    LOGGER.info(f"Hutch shutter: {hutch_shutter_state}")
    if hutch_shutter_state != ShutterState.OPEN:
        LOGGER.error(f"Hutch shutter is not open! State is {hutch_shutter_state}")
        raise Exception(f"Hutch shutter is not open! State is {hutch_shutter_state}")

    LOGGER.info(
        "Making sure aperture and beamstop are in, detector stages are in position, backlight is out, and transmission is set..."
    )
    yield from bps.mv(
        composite.aperture.position,
        AperturePositions.IN,
        composite.beamstop.pos_select,
        BeamstopPositions.DATA_COLLECTION,
        composite.det_stage.y,
        JF_DET_STAGE_Y_POSITION_MM,
        composite.backlight.backlight_position,
        BacklightPositions.OUT,
        composite.det_stage.z,
        det_z_mm,
        composite.attenuator,
        transmission_frac,
    )


def multi_rotation_plan_varying_transmission(
    composite: RotationScanComposite,
    params: MultiRotationScanByTransmissions,
):
    @bpp.set_run_key_decorator(I24PlanNameConstants.MULTI_ROTATION_SCAN)
    @run_decorator()
    def _plan_in_run_decorator():
        for transmission in params.transmission_fractions:
            param_copy = deepcopy(params).model_dump()
            del param_copy["transmission_fractions"]
            param_copy["transmission_frac"] = transmission
            single_rotation_params = SingleRotationScan(**param_copy)
            yield from single_rotation_plan(composite, single_rotation_params)

    yield from _plan_in_run_decorator()


def single_rotation_plan(
    composite: RotationScanComposite,
    params: SingleRotationScan,
):
    """A stub plan to collect diffraction images from a sample continuously rotating
    about a fixed axis - for now this axis is limited to omega.
    Needs additional setup of the sample environment and a wrapper to clean up."""

    composite.jungfrau._writer._path_info.filename = "rotation_scan" # type: ignore

    @bpp.set_run_key_decorator(I24PlanNameConstants.SINGLE_ROTATION_SCAN)
    @run_decorator()
    def _plan_in_run_decorator():
        if not params.detector_distance_mm:
            LOGGER.info(
                f"Using default detector distance of  {DEFAULT_DETECTOR_DISTANCE_MM} mm"
            )
            params.detector_distance_mm = DEFAULT_DETECTOR_DISTANCE_MM

        yield from set_up_beamline_for_rotation(
            composite, params.detector_distance_mm, params.transmission_frac
        )

        # This value isn't actually used, see https://github.com/DiamondLightSource/mx-bluesky/issues/1224
        _motor_time_to_speed = 1
        _max_velocity_deg_s = yield from bps.rd(composite.gonio.omega.max_velocity)

        motion_values = calculate_motion_profile(
            params, _motor_time_to_speed, _max_velocity_deg_s
        )

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
            _jf_trigger_info = create_jungfrau_external_triggering_info(
                params.num_images, params.detector_params.exposure_time_s
            )

            axis = composite.gonio.omega

            # can move to start as fast as possible
            yield from bps.abs_set(
                axis.velocity, motion_values.max_velocity_deg_s, wait=True
            )
            LOGGER.info(f"Moving omega to start value, {motion_values.start_scan_deg=}")
            yield from bps.abs_set(
                axis,
                motion_values.start_motion_deg,
                group=PlanGroupCheckpointConstants.ROTATION_READY_FOR_DC,
            )

            yield from setup_zebra_for_rotation(
                composite.zebra,
                composite.sample_shutter,
                axis=I24Axes.OMEGA,
                start_angle=motion_values.start_scan_deg,
                scan_width=motion_values.scan_width_deg,
                direction=motion_values.direction,
                shutter_opening_deg=motion_values.shutter_opening_deg,
                shutter_opening_s=motion_values.shutter_time_s,
                group=PlanGroupCheckpointConstants.SETUP_ZEBRA_FOR_ROTATION,
            )

            yield from bps.wait(PlanGroupCheckpointConstants.ROTATION_READY_FOR_DC)

            # Get ready for the actual scan
            yield from bps.abs_set(
                axis.velocity, motion_values.speed_for_rotation_deg_s, wait=True
            )
            yield from arm_zebra(composite.zebra)

            # Check topup gate
            yield from check_topup_and_wait_if_necessary(
                composite.synchrotron,
                motion_values.total_exposure_s,
                ops_time=10.0,  # Additional time to account for rotation, is s
            )  # See #https://github.com/DiamondLightSource/hyperion/issues/932

            # override_file_path(
            #     composite.jungfrau,
            #     f"{params.storage_directory}/{params.detector_params.full_filename}",
            # )
            

            metadata_writer = JsonMetadataWriter()

            @bpp.subs_decorator([metadata_writer])
            @bpp.set_run_key_decorator(I24PlanNameConstants.ROTATION_META_READ)
            @bpp.run_decorator(
                md={
                    "subplan_name": I24PlanNameConstants.ROTATION_META_READ,
                    "scan_points": [params.scan_points],
                    "rotation_scan_params": params.model_dump_json(),
                }
            )
            # Write metadata json file
            def _do_read():
                yield from read_devices_for_metadata(composite)

            yield from _do_read()
            yield from bps.mv(
            composite.jungfrau.drv.gain_mode,
            GainMode.DYNAMIC,
        )
            yield from fly_jungfrau(
                composite.jungfrau,
                _jf_trigger_info,
                wait=False,
                log_on_percentage_prefix="Jungfrau rotation scan triggers received",
            )

            LOGGER.info("Executing rotation scan")
            yield from bps.rel_set(
                axis,
                motion_values.distance_to_move_deg,
                wait=False,
                group=JF_COMPLETE_GROUP,
            )

            LOGGER.info(
                "Waiting for omega to finish moving and for Jungfrau to receive correct number of triggers"
            )
            yield from bps.wait(group=JF_COMPLETE_GROUP)

        yield from bpp.finalize_wrapper(
            _rotation_scan_plan(motion_values, composite),
            final_plan=partial(
                _cleanup_plan,
                composite.zebra,
                composite.jungfrau,
                composite.sample_shutter,
            ),
        )

    yield from _plan_in_run_decorator()


def _cleanup_plan(
    zebra: Zebra,
    jf: CommissioningJungfrau,
    zebra_shutter: ZebraShutter,
    group="rotation cleanup",
):
    LOGGER.info("Tidying up Zebra and Jungfrau...")
    yield from bps.unstage(jf, group=group)
    yield from tidy_up_zebra_after_rotation_scan(
        zebra, zebra_shutter, group=group, wait=False
    )
    yield from bps.wait(group=group)
