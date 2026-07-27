from collections.abc import Generator

from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp
from bluesky.utils import Msg

from dodal.devices.detector import DetectorParams
from dodal.devices.detector.detector_motion import ShutterState
from dodal.devices.mx_phase1.beamstop import BeamstopPositions
from mx_bluesky.common.device_setup_plans.position_detector import (
    set_detector_z_position,
    set_shutter,
)
from mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan import BeamlineSpecificDetectorFeatures
from mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan import \
    TGridDetectAndGridScanEssentialDevices


def start_preparing_data_collection_then_do_plan(
    beamline_specific: BeamlineSpecificDetectorFeatures,
    detector_params: DetectorParams,
    device_composite: TGridDetectAndGridScanEssentialDevices,
    detector_distance_mm: float | None,
    plan_to_run: Generator[Msg, None, None],
    group="ready_for_data_collection",
) -> Generator[Msg, None, None]:
    """Starts preparing for the next data collection and then runs the
    given plan.

     Preparation consists of:
     * Arming the Eiger
     * Moving the detector to the specified position
     * Opening the detect shutter
     If the plan fails it will disarm the eiger.
    """

    def wrapped_plan():
        yield from beamline_specific.pre_arm_detector_plan(device_composite, detector_params, group)
        yield from bps.abs_set(
            device_composite.beamstop.selected_pos, BeamstopPositions.DATA_COLLECTION, group=group
        )
        if detector_distance_mm:
            yield from set_detector_z_position(
                device_composite.detector_motion, detector_distance_mm, group
            )
        yield from set_shutter(device_composite.detector_motion, ShutterState.OPEN, group)
        yield from plan_to_run

    yield from bpp.contingency_wrapper(
        wrapped_plan(),
        except_plan=lambda e: (yield from bps.stop(device_composite.detector)),  # type: ignore # Fix types in ophyd-async (https://github.com/DiamondLightSource/mx-bluesky/issues/855)
    )
