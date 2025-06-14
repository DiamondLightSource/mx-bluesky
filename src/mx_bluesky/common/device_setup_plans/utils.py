from collections.abc import Generator

from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp
from bluesky.utils import Msg
from dodal.devices.detector.detector_motion import DetectorMotion, ShutterState
from dodal.devices.eiger import EigerDetector
from dodal.devices.mx_phase1.beamstop import Beamstop, BeamstopPositions

from mx_bluesky.common.device_setup_plans.position_detector import (
    set_detector_z_position,
    set_shutter,
)


def start_preparing_data_collection_then_do_plan(
    beamstop: Beamstop,
    eiger: EigerDetector,
    detector_motion: DetectorMotion,
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
        yield from bps.abs_set(eiger.do_arm, 1, group=group)  # type: ignore # Fix types in ophyd-async (https://github.com/DiamondLightSource/mx-bluesky/issues/855)
        yield from bps.abs_set(
            beamstop.selected_pos, BeamstopPositions.DATA_COLLECTION, group=group
        )
        if detector_distance_mm:
            yield from set_detector_z_position(
                detector_motion, detector_distance_mm, group
            )
        yield from set_shutter(detector_motion, ShutterState.OPEN, group)
        yield from plan_to_run

    yield from bpp.contingency_wrapper(
        wrapped_plan(),
        except_plan=lambda e: (yield from bps.stop(eiger)),  # type: ignore # Fix types in ophyd-async (https://github.com/DiamondLightSource/mx-bluesky/issues/855)
    )
