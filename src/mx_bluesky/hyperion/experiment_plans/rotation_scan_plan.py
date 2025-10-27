from __future__ import annotations

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
import pydantic
from blueapi.core import BlueskyContext
from bluesky.utils import MsgGenerator
from dodal.devices.aperturescatterguard import ApertureScatterguard
from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
from dodal.devices.backlight import Backlight
from dodal.devices.detector.detector_motion import DetectorMotion
from dodal.devices.eiger import EigerDetector
from dodal.devices.flux import Flux
from dodal.devices.i03 import Beamstop
from dodal.devices.i03.dcm import DCM
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.oav.oav_parameters import OAVParameters
from dodal.devices.robot import BartRobot
from dodal.devices.s4_slit_gaps import S4SlitGaps
from dodal.devices.smargon import CombinedMove, Smargon
from dodal.devices.synchrotron import Synchrotron
from dodal.devices.undulator import Undulator
from dodal.devices.xbpm_feedback import XBPMFeedback
from dodal.devices.zebra.zebra import Zebra
from dodal.devices.zebra.zebra_controlled_shutter import ZebraShutter
from dodal.plan_stubs.check_topup import check_topup_and_wait_if_necessary
from dodal.plans.preprocessors.verify_undulator_gap import (
    verify_undulator_gap_before_run_decorator,
)

from mx_bluesky.common.device_setup_plans.manipulate_sample import (
    cleanup_sample_environment,
    setup_sample_environment,
)
from mx_bluesky.common.device_setup_plans.setup_zebra_and_shutter import (
    setup_zebra_for_rotation,
    tidy_up_zebra_after_rotation_scan,
)
from mx_bluesky.common.device_setup_plans.utils import (
    start_preparing_data_collection_then_do_plan,
)
from mx_bluesky.common.experiment_plans.inner_plans.read_hardware import (
    read_hardware_for_zocalo,
    standard_read_hardware_during_collection,
    standard_read_hardware_pre_collection,
)
from mx_bluesky.common.experiment_plans.oav_snapshot_plan import (
    OavSnapshotComposite,
    oav_snapshot_plan,
    setup_beamline_for_oav,
)
from mx_bluesky.common.experiment_plans.rotation.rotation_utils import (
    RotationMotionProfile,
    calculate_motion_profile,
)
from mx_bluesky.common.experiment_plans.setup_zebra import (
    arm_zebra,
)
from mx_bluesky.common.parameters.components import WithSnapshot
from mx_bluesky.common.parameters.rotation import (
    RotationScan,
    SingleRotationScan,
)
from mx_bluesky.common.preprocessors.preprocessors import (
    transmission_and_xbpm_feedback_for_collection_decorator,
)
from mx_bluesky.common.utils.context import device_composite_from_context
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.hyperion.parameters.constants import CONST


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class RotationScanComposite(OavSnapshotComposite):
    """All devices which are directly or indirectly required by this plan"""

    aperture_scatterguard: ApertureScatterguard
    attenuator: BinaryFilterAttenuator
    backlight: Backlight
    beamstop: Beamstop
    dcm: DCM
    detector_motion: DetectorMotion
    eiger: EigerDetector
    flux: Flux
    robot: BartRobot
    smargon: Smargon
    undulator: Undulator
    synchrotron: Synchrotron
    s4_slit_gaps: S4SlitGaps
    sample_shutter: ZebraShutter
    zebra: Zebra
    oav: OAV
    xbpm_feedback: XBPMFeedback


def create_devices(context: BlueskyContext) -> RotationScanComposite:
    """Ensures necessary devices have been instantiated"""

    return device_composite_from_context(context, RotationScanComposite)


def rotation_scan_plan(
    composite: RotationScanComposite,
    params: SingleRotationScan,
    motion_values: RotationMotionProfile,
):
    """A stub plan to collect diffraction images from a sample continuously rotating
    about a fixed axis - for now this axis is limited to omega.
    Needs additional setup of the sample environment and a wrapper to clean up."""

    @bpp.set_run_key_decorator(CONST.PLAN.ROTATION_MAIN)
    @bpp.run_decorator(
        md={
            "subplan_name": CONST.PLAN.ROTATION_MAIN,
            "scan_points": [params.scan_points],
        }
    )
    def _rotation_scan_plan(
        motion_values: RotationMotionProfile,
        composite: RotationScanComposite,
    ):
        axis = composite.smargon.omega

        # can move to start as fast as possible
        yield from bps.abs_set(
            axis.velocity, motion_values.max_velocity_deg_s, wait=True
        )
        LOGGER.info(f"moving omega to beginning, {motion_values.start_scan_deg=}")
        yield from bps.abs_set(
            axis,
            motion_values.start_motion_deg,
            group=CONST.WAIT.ROTATION_READY_FOR_DC,
        )

        yield from setup_zebra_for_rotation(
            composite.zebra,
            composite.sample_shutter,
            start_angle=motion_values.start_scan_deg,
            scan_width=motion_values.scan_width_deg,
            direction=motion_values.direction,
            shutter_opening_deg=motion_values.shutter_opening_deg,
            shutter_opening_s=motion_values.shutter_time_s,
            group="setup_zebra",
        )

        yield from setup_sample_environment(
            composite.aperture_scatterguard,
            params.selected_aperture,
            composite.backlight,
            group=CONST.WAIT.ROTATION_READY_FOR_DC,
        )

        LOGGER.info("Wait for any previous moves...")
        # wait for all the setup tasks at once
        yield from bps.wait(CONST.WAIT.ROTATION_READY_FOR_DC)
        yield from bps.wait(CONST.WAIT.MOVE_GONIO_TO_START)

        # get some information for the ispyb deposition and trigger the callback
        yield from read_hardware_for_zocalo(composite.eiger)

        yield from standard_read_hardware_pre_collection(
            composite.undulator,
            composite.synchrotron,
            composite.s4_slit_gaps,
            composite.dcm,
            composite.smargon,
        )

        # Get ready for the actual scan
        yield from bps.abs_set(
            axis.velocity, motion_values.speed_for_rotation_deg_s, wait=True
        )

        yield from bps.wait("setup_zebra")
        yield from arm_zebra(composite.zebra)

        # Check topup gate
        yield from check_topup_and_wait_if_necessary(
            composite.synchrotron,
            motion_values.total_exposure_s,
            ops_time=10.0,  # Additional time to account for rotation, is s
        )  # See #https://github.com/DiamondLightSource/hyperion/issues/932

        LOGGER.info("Executing rotation scan")
        yield from bps.rel_set(axis, motion_values.distance_to_move_deg, wait=True)

        yield from standard_read_hardware_during_collection(
            composite.aperture_scatterguard,
            composite.attenuator,
            composite.flux,
            composite.dcm,
            composite.eiger,
        )

    yield from _rotation_scan_plan(motion_values, composite)


def _cleanup_plan(composite: RotationScanComposite, **kwargs):
    LOGGER.info("Cleaning up after rotation scan")
    max_vel = yield from bps.rd(composite.smargon.omega.max_velocity)
    yield from cleanup_sample_environment(composite.detector_motion, group="cleanup")
    yield from bps.abs_set(composite.smargon.omega.velocity, max_vel, group="cleanup")
    yield from tidy_up_zebra_after_rotation_scan(
        composite.zebra, composite.sample_shutter, group="cleanup", wait=False
    )
    yield from bps.wait("cleanup")


def _move_and_rotation(
    composite: RotationScanComposite,
    params: SingleRotationScan,
    oav_params: OAVParameters,
):
    motor_time_to_speed = yield from bps.rd(composite.smargon.omega.acceleration_time)
    max_vel = yield from bps.rd(composite.smargon.omega.max_velocity)
    motion_values = calculate_motion_profile(params, motor_time_to_speed, max_vel)

    def _div_by_1000_if_not_none(num: float | None):
        return num / 1000 if num else num

    LOGGER.info("moving to position (if specified)")
    yield from bps.abs_set(
        composite.smargon,
        CombinedMove(
            x=_div_by_1000_if_not_none(params.x_start_um),
            y=_div_by_1000_if_not_none(params.y_start_um),
            z=_div_by_1000_if_not_none(params.z_start_um),
            phi=params.phi_start_deg,
            chi=params.chi_start_deg,
        ),
        group=CONST.WAIT.MOVE_GONIO_TO_START,
    )

    if params.take_snapshots:
        yield from bps.wait(CONST.WAIT.MOVE_GONIO_TO_START)

        if not params.use_grid_snapshots:
            yield from setup_beamline_for_oav(
                composite.smargon,
                composite.backlight,
                composite.aperture_scatterguard,
                wait=True,
            )

        if params.selected_aperture:
            yield from bps.prepare(
                composite.aperture_scatterguard,
                params.selected_aperture,
                group=CONST.WAIT.PREPARE_APERTURE,
            )
        yield from oav_snapshot_plan(composite, params, oav_params)
    yield from rotation_scan_plan(composite, params, motion_values)


def rotation_scan(
    composite: RotationScanComposite,
    parameters: RotationScan,
    oav_params: OAVParameters | None = None,
) -> MsgGenerator:
    @bpp.set_run_key_decorator(CONST.PLAN.ROTATION_MULTI_OUTER)
    @bpp.run_decorator(
        md={
            "activate_callbacks": ["BeamDrawingCallback"],
            "with_snapshot": parameters.model_dump_json(
                include=WithSnapshot.model_fields.keys()  # type: ignore
            ),
        }
    )
    def _wrapped_rotation_scan():
        yield from rotation_scan_internal(composite, parameters, oav_params)

    yield from _wrapped_rotation_scan()


def rotation_scan_internal(
    composite: RotationScanComposite,
    parameters: RotationScan,
    oav_params: OAVParameters | None = None,
) -> MsgGenerator:
    if not oav_params:
        oav_params = OAVParameters(context="xrayCentring")
    eiger: EigerDetector = composite.eiger
    eiger.set_detector_parameters(parameters.detector_params)

    @transmission_and_xbpm_feedback_for_collection_decorator(
        composite,
        parameters.transmission_frac,
    )
    @bpp.set_run_key_decorator("multi_rotation_scan")
    @bpp.run_decorator(
        md={
            "subplan_name": CONST.PLAN.ROTATION_MULTI,
            "full_num_of_images": parameters.num_images,
            "meta_data_run_number": parameters.detector_params.run_number,
            "activate_callbacks": [
                "RotationISPyBCallback",
                "RotationNexusFileCallback",
            ],
        }
    )
    @bpp.finalize_decorator(lambda: _cleanup_plan(composite))
    def _multi_rotation_scan():
        for single_scan in parameters.single_rotation_scans:

            @verify_undulator_gap_before_run_decorator(composite)
            @bpp.set_run_key_decorator("rotation_scan")
            @bpp.run_decorator(  # attach experiment metadata to the start document
                md={
                    "subplan_name": CONST.PLAN.ROTATION_OUTER,
                    "mx_bluesky_parameters": single_scan.model_dump_json(),
                }
            )
            def rotation_scan_core(
                params: SingleRotationScan,
            ):
                yield from _move_and_rotation(composite, params, oav_params)

            yield from rotation_scan_core(single_scan)

        yield from bps.unstage(eiger, wait=True)

    LOGGER.info("setting up and staging eiger...")
    yield from start_preparing_data_collection_then_do_plan(
        composite.beamstop,
        eiger,
        composite.detector_motion,
        parameters.detector_distance_mm,
        _multi_rotation_scan(),
        group=CONST.WAIT.ROTATION_READY_FOR_DC,
    )
