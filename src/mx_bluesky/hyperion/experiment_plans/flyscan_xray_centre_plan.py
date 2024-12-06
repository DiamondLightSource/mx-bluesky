from __future__ import annotations

import dataclasses
from collections.abc import Callable, Sequence
from functools import partial
from pathlib import Path
from typing import Protocol

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
import numpy as np
import pydantic
from blueapi.core import BlueskyContext
from bluesky.callbacks import CallbackBase
from bluesky.utils import MsgGenerator
from dodal.devices.aperturescatterguard import (
    ApertureScatterguard,
)
from dodal.devices.attenuator import Attenuator
from dodal.devices.backlight import Backlight
from dodal.devices.dcm import DCM
from dodal.devices.eiger import EigerDetector
from dodal.devices.fast_grid_scan import (
    FastGridScanCommon,
    PandAFastGridScan,
    ZebraFastGridScan,
)
from dodal.devices.fast_grid_scan import (
    set_fast_grid_scan_params as set_flyscan_params,
)
from dodal.devices.flux import Flux
from dodal.devices.robot import BartRobot
from dodal.devices.s4_slit_gaps import S4SlitGaps
from dodal.devices.smargon import Smargon
from dodal.devices.synchrotron import Synchrotron
from dodal.devices.undulator import Undulator
from dodal.devices.xbpm_feedback import XBPMFeedback
from dodal.devices.zebra import Zebra
from dodal.devices.zebra_controlled_shutter import ZebraShutter
from dodal.devices.zocalo.zocalo_results import (
    ZOCALO_READING_PLAN_NAME,
    ZOCALO_STAGE_GROUP,
    XrcResult,
    ZocaloResults,
    get_full_processing_results,
)
from event_model import RunStart
from ophyd_async.fastcs.panda import HDFPanda

from mx_bluesky.common.plans.do_fgs import kickoff_and_complete_gridscan
from mx_bluesky.common.utils.tracing import TRACER
from mx_bluesky.hyperion.device_setup_plans.read_hardware_for_setup import (
    read_hardware_during_collection,
    read_hardware_pre_collection,
)
from mx_bluesky.hyperion.device_setup_plans.setup_panda import (
    disarm_panda_for_gridscan,
    set_panda_directory,
    setup_panda_for_flyscan,
)
from mx_bluesky.hyperion.device_setup_plans.setup_zebra import (
    setup_zebra_for_gridscan,
    setup_zebra_for_panda_flyscan,
    tidy_up_zebra_after_gridscan,
)
from mx_bluesky.hyperion.device_setup_plans.xbpm_feedback import (
    transmission_and_xbpm_feedback_for_collection_decorator,
)
from mx_bluesky.hyperion.exceptions import CrystalNotFoundException, SampleException
from mx_bluesky.hyperion.experiment_plans.change_aperture_then_move_plan import (
    change_aperture_then_move_to_xtal,
)
from mx_bluesky.hyperion.experiment_plans.common.xrc_result import XRayCentreResult
from mx_bluesky.hyperion.external_interaction.callbacks.xray_centre.ispyb_callback import (
    ispyb_activation_wrapper,
)
from mx_bluesky.hyperion.log import LOGGER
from mx_bluesky.hyperion.parameters.constants import CONST
from mx_bluesky.hyperion.parameters.gridscan import HyperionThreeDGridScan
from mx_bluesky.hyperion.utils.context import device_composite_from_context

ZOCALO_MIN_TOTAL_COUNT_THRESHOLD = 3


class SmargonSpeedException(Exception):
    pass


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class FlyScanXRayCentreComposite:
    """All devices which are directly or indirectly required by this plan"""

    aperture_scatterguard: ApertureScatterguard
    attenuator: Attenuator
    backlight: Backlight
    dcm: DCM
    eiger: EigerDetector
    zebra_fast_grid_scan: ZebraFastGridScan
    flux: Flux
    s4_slit_gaps: S4SlitGaps
    smargon: Smargon
    undulator: Undulator
    synchrotron: Synchrotron
    xbpm_feedback: XBPMFeedback
    zebra: Zebra
    zocalo: ZocaloResults
    panda: HDFPanda
    panda_fast_grid_scan: PandAFastGridScan
    robot: BartRobot
    sample_shutter: ZebraShutter

    @property
    def sample_motors(self) -> Smargon:
        """Convenience alias with a more user-friendly name"""
        return self.smargon


class XRayCentreEventHandler(CallbackBase):
    def __init__(self):
        super().__init__()
        self.xray_centre_results: Sequence[XRayCentreResult] | None = None

    def start(self, doc: RunStart) -> RunStart | None:
        if "xray_centre_results" in doc:
            self.xray_centre_results = [
                XRayCentreResult(**result_dict)
                for result_dict in doc["xray_centre_results"]  # type: ignore
            ]
        return doc


def create_devices(context: BlueskyContext) -> FlyScanXRayCentreComposite:
    """Creates the devices required for the plan and connect to them"""
    return device_composite_from_context(context, FlyScanXRayCentreComposite)


def flyscan_xray_centre_no_move(
    composite: FlyScanXRayCentreComposite, parameters: HyperionThreeDGridScan
) -> MsgGenerator:
    """Perform a flyscan and determine the centres of interest"""
    parameters.features.update_self_from_server()
    composite.eiger.set_detector_parameters(parameters.detector_params)
    composite.zocalo.zocalo_environment = CONST.ZOCALO_ENV
    composite.zocalo.use_cpu_and_gpu = parameters.features.compare_cpu_and_gpu_zocalo

    feature_controlled = _get_feature_controlled(composite, parameters)

    @bpp.set_run_key_decorator(CONST.PLAN.GRIDSCAN_OUTER)
    @bpp.run_decorator(  # attach experiment metadata to the start document
        md={
            "subplan_name": CONST.PLAN.GRIDSCAN_OUTER,
            "hyperion_parameters": parameters.model_dump_json(),
            "activate_callbacks": [
                "GridscanNexusFileCallback",
            ],
        }
    )
    @bpp.finalize_decorator(lambda: feature_controlled.tidy_plan(composite))
    @transmission_and_xbpm_feedback_for_collection_decorator(
        composite.xbpm_feedback,
        composite.attenuator,
        parameters.transmission_frac,
    )
    def run_gridscan_and_fetch_and_tidy(
        fgs_composite: FlyScanXRayCentreComposite,
        params: HyperionThreeDGridScan,
        feature_controlled: _FeatureControlled,
    ) -> MsgGenerator:
        yield from run_gridscan_and_fetch_results(
            fgs_composite, params, feature_controlled
        )

    yield from run_gridscan_and_fetch_and_tidy(
        composite, parameters, feature_controlled
    )


def flyscan_xray_centre(
    composite: FlyScanXRayCentreComposite,
    parameters: HyperionThreeDGridScan,
) -> MsgGenerator:
    """Create the plan to run the grid scan based on provided parameters.

    The ispyb handler should be added to the whole gridscan as we want to capture errors
    at any point in it.

    Args:
        parameters (ThreeDGridScan): The parameters to run the scan.

    Returns:
        Generator: The plan for the gridscan
    """
    xrc_event_handler = XRayCentreEventHandler()

    @bpp.subs_decorator(xrc_event_handler)
    def flyscan_and_fetch_results() -> MsgGenerator:
        yield from ispyb_activation_wrapper(
            flyscan_xray_centre_no_move(composite, parameters), parameters
        )

    yield from flyscan_and_fetch_results()

    xray_centre_results = xrc_event_handler.xray_centre_results
    assert (
        xray_centre_results
    ), "Flyscan result event not received or no crystal found and exception not raised"
    yield from change_aperture_then_move_to_xtal(
        xray_centre_results[0],
        composite.smargon,
        composite.aperture_scatterguard,
        parameters,
    )


@bpp.set_run_key_decorator(CONST.PLAN.GRIDSCAN_AND_MOVE)
@bpp.run_decorator(md={"subplan_name": CONST.PLAN.GRIDSCAN_AND_MOVE})
def run_gridscan_and_fetch_results(
    fgs_composite: FlyScanXRayCentreComposite,
    parameters: HyperionThreeDGridScan,
    feature_controlled: _FeatureControlled,
) -> MsgGenerator:
    """A multi-run plan which runs a gridscan, gets the results from zocalo
    and fires an event with the centres of mass determined by zocalo"""

    # We get the initial motor positions so we can return to them on zocalo failure
    initial_xyz = np.array(
        [
            (yield from bps.rd(fgs_composite.sample_motors.x)),
            (yield from bps.rd(fgs_composite.sample_motors.y)),
            (yield from bps.rd(fgs_composite.sample_motors.z)),
        ]
    )

    yield from feature_controlled.setup_trigger(fgs_composite, parameters, initial_xyz)

    LOGGER.info("Starting grid scan")
    yield from bps.stage(
        fgs_composite.zocalo, group=ZOCALO_STAGE_GROUP
    )  # connect to zocalo and make sure the queue is clear
    yield from run_gridscan(fgs_composite, parameters, feature_controlled)

    LOGGER.info("Grid scan finished, getting results.")

    try:
        with TRACER.start_span("wait_for_zocalo"):
            yield from bps.trigger_and_read(
                [fgs_composite.zocalo], name=ZOCALO_READING_PLAN_NAME
            )
            LOGGER.info("Zocalo triggered and read, interpreting results.")
            xrc_results = yield from get_full_processing_results(fgs_composite.zocalo)
            LOGGER.info(f"Got xray centres, top 5: {xrc_results[:5]}")
            filtered_results = [
                result
                for result in xrc_results
                if result["total_count"] >= ZOCALO_MIN_TOTAL_COUNT_THRESHOLD
            ]
            discarded_count = len(xrc_results) - len(filtered_results)
            if discarded_count > 0:
                LOGGER.info(
                    f"Removed {discarded_count} results because below threshold"
                )
            if filtered_results:
                flyscan_results = [
                    _xrc_result_in_boxes_to_result_in_mm(xr, parameters)
                    for xr in filtered_results
                ]
            else:
                LOGGER.warning("No X-ray centre received")
                raise CrystalNotFoundException()
            yield from _fire_xray_centre_result_event(flyscan_results)

    finally:
        # Turn off dev/shm streaming to avoid filling disk, see https://github.com/DiamondLightSource/hyperion/issues/1395
        LOGGER.info("Turning off Eiger dev/shm streaming")
        yield from bps.abs_set(fgs_composite.eiger.odin.fan.dev_shm_enable, 0)  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809

        # Wait on everything before returning to GDA (particularly apertures), can be removed
        # when we do not return to GDA here
        yield from bps.wait()


def _xrc_result_in_boxes_to_result_in_mm(
    xrc_result: XrcResult, parameters: HyperionThreeDGridScan
) -> XRayCentreResult:
    fgs_params = parameters.FGS_params
    xray_centre = fgs_params.grid_position_to_motor_position(
        np.array(xrc_result["centre_of_mass"])
    )
    return XRayCentreResult(
        centre_of_mass_mm=xray_centre,
        bounding_box_mm=(
            fgs_params.grid_position_to_motor_position(
                np.array(xrc_result["bounding_box"][0])
            ),
            fgs_params.grid_position_to_motor_position(
                np.array(xrc_result["bounding_box"][1])
            ),
        ),
        max_count=xrc_result["max_count"],
        total_count=xrc_result["total_count"],
    )


@bpp.set_run_key_decorator(CONST.PLAN.FLYSCAN_RESULTS)
def _fire_xray_centre_result_event(results: Sequence[XRayCentreResult]):
    def empty_plan():
        return iter([])

    yield from bpp.run_wrapper(
        empty_plan(),
        md={"xray_centre_results": [dataclasses.asdict(r) for r in results]},
    )


@bpp.set_run_key_decorator(CONST.PLAN.GRIDSCAN_MAIN)
@bpp.run_decorator(md={"subplan_name": CONST.PLAN.GRIDSCAN_MAIN})
def run_gridscan(
    fgs_composite: FlyScanXRayCentreComposite,
    parameters: HyperionThreeDGridScan,
    feature_controlled: _FeatureControlled,
    md={  # noqa
        "plan_name": CONST.PLAN.GRIDSCAN_MAIN,
    },
):
    sample_motors = fgs_composite.sample_motors

    # Currently gridscan only works for omega 0, see #
    with TRACER.start_span("moving_omega_to_0"):
        yield from bps.abs_set(sample_motors.omega, 0)

    # We only subscribe to the communicator callback for run_gridscan, so this is where
    # we should generate an event reading the values which need to be included in the
    # ispyb deposition
    with TRACER.start_span("ispyb_hardware_readings"):
        yield from read_hardware_pre_collection(
            fgs_composite.undulator,
            fgs_composite.synchrotron,
            fgs_composite.s4_slit_gaps,
            fgs_composite.dcm,
            fgs_composite.smargon,
        )

    read_during_collection = partial(
        read_hardware_during_collection,
        fgs_composite.aperture_scatterguard,
        fgs_composite.attenuator,
        fgs_composite.flux,
        fgs_composite.dcm,
        fgs_composite.eiger,
    )

    LOGGER.info("Setting fgs params")
    yield from feature_controlled.set_flyscan_params()

    LOGGER.info("Waiting for gridscan validity check")
    yield from wait_for_gridscan_valid(feature_controlled.fgs_motors)

    LOGGER.info("Waiting for arming to finish")
    yield from bps.wait(CONST.WAIT.GRID_READY_FOR_DC)
    yield from bps.stage(fgs_composite.eiger)  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809

    yield from kickoff_and_complete_gridscan(
        feature_controlled.fgs_motors,
        fgs_composite.eiger,
        fgs_composite.synchrotron,
        [parameters.scan_points_first_grid, parameters.scan_points_second_grid],
        parameters.scan_indices,
        plan_during_collection=read_during_collection,
    )
    yield from bps.abs_set(feature_controlled.fgs_motors.z_steps, 0, wait=False)


def wait_for_gridscan_valid(fgs_motors: FastGridScanCommon, timeout=0.5):
    LOGGER.info("Waiting for valid fgs_params")
    SLEEP_PER_CHECK = 0.1
    times_to_check = int(timeout / SLEEP_PER_CHECK)
    for _ in range(times_to_check):
        scan_invalid = yield from bps.rd(fgs_motors.scan_invalid)
        pos_counter = yield from bps.rd(fgs_motors.position_counter)
        LOGGER.debug(
            f"Scan invalid: {scan_invalid} and position counter: {pos_counter}"
        )
        if not scan_invalid and pos_counter == 0:
            LOGGER.info("Gridscan scan valid and position counter reset")
            return
        yield from bps.sleep(SLEEP_PER_CHECK)
    raise SampleException("Scan invalid - pin too long/short/bent and out of range")


@dataclasses.dataclass
class _FeatureControlled:
    class _ZebraSetup(Protocol):
        def __call__(
            self, zebra: Zebra, group="setup_zebra_for_gridscan", wait=True
        ) -> MsgGenerator: ...

    class _ExtraSetup(Protocol):
        def __call__(
            self,
            fgs_composite: FlyScanXRayCentreComposite,
            parameters: HyperionThreeDGridScan,
            initial_xyz: np.ndarray,
        ) -> MsgGenerator: ...

    setup_trigger: _ExtraSetup
    tidy_plan: Callable[[FlyScanXRayCentreComposite], MsgGenerator]
    set_flyscan_params: Callable[[], MsgGenerator]
    fgs_motors: FastGridScanCommon


def _get_feature_controlled(
    fgs_composite: FlyScanXRayCentreComposite,
    parameters: HyperionThreeDGridScan,
):
    if parameters.features.use_panda_for_gridscan:
        return _FeatureControlled(
            setup_trigger=_panda_triggering_setup,
            tidy_plan=_panda_tidy,
            set_flyscan_params=partial(
                set_flyscan_params,
                fgs_composite.panda_fast_grid_scan,
                parameters.panda_FGS_params,
            ),
            fgs_motors=fgs_composite.panda_fast_grid_scan,
        )
    else:
        return _FeatureControlled(
            setup_trigger=_zebra_triggering_setup,
            tidy_plan=partial(_generic_tidy, group="flyscan_zebra_tidy", wait=True),
            set_flyscan_params=partial(
                set_flyscan_params,
                fgs_composite.zebra_fast_grid_scan,
                parameters.FGS_params,
            ),
            fgs_motors=fgs_composite.zebra_fast_grid_scan,
        )


def _generic_tidy(
    fgs_composite: FlyScanXRayCentreComposite, group, wait=True
) -> MsgGenerator:
    LOGGER.info("Tidying up Zebra")
    yield from tidy_up_zebra_after_gridscan(
        fgs_composite.zebra, fgs_composite.sample_shutter, group=group, wait=wait
    )
    LOGGER.info("Tidying up Zocalo")
    # make sure we don't consume any other results
    yield from bps.unstage(fgs_composite.zocalo, group=group, wait=wait)


def _panda_tidy(fgs_composite: FlyScanXRayCentreComposite):
    group = "panda_flyscan_tidy"
    LOGGER.info("Disabling panda blocks")
    yield from disarm_panda_for_gridscan(fgs_composite.panda, group)
    yield from _generic_tidy(fgs_composite, group, False)
    yield from bps.wait(group, timeout=10)
    yield from bps.unstage(fgs_composite.panda)


def _zebra_triggering_setup(
    fgs_composite: FlyScanXRayCentreComposite,
    parameters: HyperionThreeDGridScan,
    initial_xyz: np.ndarray,
):
    yield from setup_zebra_for_gridscan(
        fgs_composite.zebra, fgs_composite.sample_shutter, wait=True
    )


def _panda_triggering_setup(
    fgs_composite: FlyScanXRayCentreComposite,
    parameters: HyperionThreeDGridScan,
    initial_xyz: np.ndarray,
):
    LOGGER.info("Setting up Panda for flyscan")

    run_up_distance_mm = yield from bps.rd(
        fgs_composite.panda_fast_grid_scan.run_up_distance_mm
    )

    # Set the time between x steps pv
    DEADTIME_S = 1e-6  # according to https://www.dectris.com/en/detectors/x-ray-detectors/eiger2/eiger2-for-synchrotrons/eiger2-x/

    time_between_x_steps_ms = (DEADTIME_S + parameters.exposure_time_s) * 1e3

    smargon_speed_limit_mm_per_s = yield from bps.rd(
        fgs_composite.smargon.x.max_velocity
    )

    sample_velocity_mm_per_s = (
        parameters.panda_FGS_params.x_step_size_mm * 1e3 / time_between_x_steps_ms
    )
    if sample_velocity_mm_per_s > smargon_speed_limit_mm_per_s:
        raise SmargonSpeedException(
            f"Smargon speed was calculated from x step size\
            {parameters.panda_FGS_params.x_step_size_mm}mm and\
            time_between_x_steps_ms {time_between_x_steps_ms} as\
            {sample_velocity_mm_per_s}mm/s. The smargon's speed limit is\
            {smargon_speed_limit_mm_per_s}mm/s."
        )
    else:
        LOGGER.info(
            f"Panda grid scan: Smargon speed set to {smargon_speed_limit_mm_per_s} mm/s"
            f" and using a run-up distance of {run_up_distance_mm}"
        )

    yield from bps.mv(
        fgs_composite.panda_fast_grid_scan.time_between_x_steps_ms,  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
        time_between_x_steps_ms,  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
    )

    directory_provider_root = Path(parameters.storage_directory)
    yield from set_panda_directory(directory_provider_root)

    yield from setup_panda_for_flyscan(
        fgs_composite.panda,
        parameters.panda_FGS_params,
        initial_xyz[0],
        parameters.exposure_time_s,
        time_between_x_steps_ms,
        sample_velocity_mm_per_s,
    )

    LOGGER.info("Setting up Zebra for panda flyscan")
    yield from setup_zebra_for_panda_flyscan(
        fgs_composite.zebra, fgs_composite.sample_shutter, wait=True
    )
