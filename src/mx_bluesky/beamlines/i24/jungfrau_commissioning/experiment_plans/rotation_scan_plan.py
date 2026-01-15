from functools import partial

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
from bluesky.preprocessors import run_decorator
from bluesky.utils import MsgGenerator
from dodal.devices.hutch_shutter import ShutterState
from dodal.devices.i24.aperture import AperturePositions
from dodal.devices.i24.beamstop import BeamstopPositions
from dodal.devices.i24.commissioning_jungfrau import CommissioningJungfrau
from dodal.devices.i24.dual_backlight import BacklightPositions
from dodal.devices.zebra.zebra import ArmDemand, I24Axes, Zebra
from dodal.devices.zebra.zebra_controlled_shutter import ZebraShutter
from ophyd_async.fastcs.jungfrau import (
    GainMode,
    create_jungfrau_external_triggering_info,
)
from pydantic import BaseModel, field_validator

from mx_bluesky.beamlines.i24.jungfrau_commissioning.callbacks.metadata_writer import (
    JsonMetadataWriter,
)
from mx_bluesky.beamlines.i24.jungfrau_commissioning.composites import (
    RotationScanComposite,
)
from mx_bluesky.beamlines.i24.jungfrau_commissioning.plan_stubs.plan_utils import (
    JF_COMPLETE_GROUP,
    fly_jungfrau,
)
from mx_bluesky.beamlines.i24.parameters.constants import (
    PlanNameConstants,
)
from mx_bluesky.common.device_setup_plans.setup_zebra_and_shutter import (
    setup_zebra_for_rotation,
    tidy_up_zebra_after_rotation_scan,
)
from mx_bluesky.common.experiment_plans.inner_plans.read_hardware import (
    read_hardware_plan,
)
from mx_bluesky.common.experiment_plans.rotation.rotation_utils import (
    RotationMotionProfile,
    calculate_motion_profile,
)
from mx_bluesky.common.parameters.components import PARAMETER_VERSION
from mx_bluesky.common.parameters.constants import (
    USE_NUMTRACKER,
    PlanGroupCheckpointConstants,
)
from mx_bluesky.common.parameters.rotation import (
    SingleRotationScan,
)
from mx_bluesky.common.utils.log import LOGGER

READING_DUMP_FILENAME = "collection_info.json"

# Should be read from config file, see
# https://github.com/DiamondLightSource/mx-bluesky/issues/1502
JF_DET_STAGE_Y_POSITION_MM = 730
DEFAULT_DETECTOR_DISTANCE_MM = 200


class ExternalRotationScanParams(BaseModel):
    transmission_fractions: list[float]
    exposure_time_s: float
    omega_start_deg: float = 0
    rotation_increment_per_image_deg: float = 0.1
    filename: str = "rotations"
    detector_distance_mm: float = DEFAULT_DETECTOR_DISTANCE_MM
    sample_id: int

    @field_validator("transmission_fractions")
    @classmethod
    def validate_transmission_fractions(cls, values):
        for v in values:
            if not 0 <= v <= 1:
                raise ValueError(
                    f"All transmission fractions must be between 0 and 1; got {v}"
                )
        return values


def _get_internal_rotation_params(
    entry_params: ExternalRotationScanParams, transmission: float
) -> SingleRotationScan:
    return SingleRotationScan(
        sample_id=entry_params.sample_id,
        visit=USE_NUMTRACKER,  # See https://github.com/DiamondLightSource/mx-bluesky/issues/1527
        parameter_model_version=PARAMETER_VERSION,
        file_name=entry_params.filename,
        transmission_frac=transmission,
        exposure_time_s=entry_params.exposure_time_s,
        storage_directory=USE_NUMTRACKER,
    )


class HutchClosedError(Exception): ...


def rotation_scan_plan(
    composite: RotationScanComposite, params: ExternalRotationScanParams
) -> MsgGenerator:
    """BlueAPI entry point for i24 JF rotation scans"""

    for transmission in params.transmission_fractions:
        rotation_params = _get_internal_rotation_params(params, transmission)
        yield from single_rotation_plan(composite, rotation_params)


def set_up_beamline_for_rotation(
    composite: RotationScanComposite,
    det_z_mm: float,
    transmission_frac: float,
):
    """Check hutch is open, then, in parallel, move backlight in,
    move aperture in, move beamstop out and move det stages in. Wait for this parallel
    move to finish."""

    hutch_shutter_state: ShutterState = yield from bps.rd(
        composite.hutch_shutter.status
    )
    LOGGER.info(f"Hutch shutter: {hutch_shutter_state}")
    if hutch_shutter_state != ShutterState.OPEN:
        LOGGER.error(f"Hutch shutter is not open! State is {hutch_shutter_state}")
        raise HutchClosedError(
            f"Hutch shutter is not open! State is {hutch_shutter_state}"
        )

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


def single_rotation_plan(
    composite: RotationScanComposite,
    params: SingleRotationScan,
):
    """A stub plan to collect diffraction images from a sample continuously rotating
    about a fixed axis - for now this axis is limited to omega.
    Needs additional setup of the sample environment and a wrapper to clean up."""

    @bpp.set_run_key_decorator(PlanNameConstants.SINGLE_ROTATION_SCAN)
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

        # Callback which intercepts read documents and writes to json file,
        # used for saving device metadata
        metadata_writer = JsonMetadataWriter()

        @bpp.subs_decorator([metadata_writer])
        @bpp.set_run_key_decorator(PlanNameConstants.ROTATION_MAIN)
        @bpp.run_decorator(
            md={
                "subplan_name": PlanNameConstants.ROTATION_MAIN,
                "scan_points": [params.scan_points],
                "rotation_scan_params": params.model_dump_json(),
                "detector_file_template": params.file_name,
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
            )

            yield from bps.wait(PlanGroupCheckpointConstants.ROTATION_READY_FOR_DC)

            # Get ready for the actual scan
            yield from bps.abs_set(
                axis.velocity, motion_values.speed_for_rotation_deg_s, wait=True
            )
            yield from bps.abs_set(composite.zebra.pc.arm, ArmDemand.ARM, wait=True)

            # Should check topup gate here, but not yet implemented,
            # see https://github.com/DiamondLightSource/mx-bluesky/issues/1501

            # Read hardware after preparing jungfrau so that device metadata output from callback is correct
            # Whilst metadata is being written in bluesky we need to access the private writer here
            read_hardware_partial = partial(
                read_hardware_plan,
                [
                    composite.dcm.energy_in_keV,
                    composite.dcm.wavelength_in_a,
                    composite.det_stage.z,
                    composite.jungfrau._writer.file_path,  # noqa: SLF001 N
                ],
                PlanNameConstants.ROTATION_DEVICE_READ,
            )

            yield from fly_jungfrau(
                composite.jungfrau,
                _jf_trigger_info,
                GainMode.DYNAMIC,
                wait=False,
                log_on_percentage_prefix="Jungfrau rotation scan triggers received",
                read_hardware_after_prepare_plan=read_hardware_partial,
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
