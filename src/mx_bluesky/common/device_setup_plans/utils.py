from __future__ import annotations

from collections.abc import Generator
from typing import Any, Protocol

from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp
from bluesky.utils import Msg
from dodal.devices.aperturescatterguard import ApertureScatterguard
from dodal.devices.detector import DetectorParams
from dodal.devices.detector.detector_motion import DetectorMotion, ShutterState
from dodal.devices.mx_phase1.beamstop import Beamstop, BeamstopPositions
from dodal.devices.smargon import Smargon
from dodal.devices.synchrotron import Synchrotron

from mx_bluesky.common.device_setup_plans.detector.beamline_specific import (
    BeamlineSpecificDetectorFeatures,
    DiffractionEssentialDevices,
    TDetector,
)
from mx_bluesky.common.device_setup_plans.position_detector import (
    set_detector_z_position,
    set_shutter,
)


class DiffractionExtendedDevices(
    DiffractionEssentialDevices[Smargon, TDetector],
    Protocol[TDetector],
):
    """An extended set of devices for running a diffraction experiment plan which
    manages some additional diffraction parameters and retrieves results."""

    synchrotron: Synchrotron
    gonio: Smargon
    aperture_scatterguard: ApertureScatterguard
    beamstop: Beamstop
    detector_motion: DetectorMotion


def start_preparing_data_collection_then_do_plan(
    beamline_specific: BeamlineSpecificDetectorFeatures,
    detector_params: DetectorParams,
    device_composite: DiffractionExtendedDevices[Any],
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
        yield from beamline_specific.pre_arm_detector_plan(
            device_composite, detector_params, group
        )
        yield from bps.abs_set(
            device_composite.beamstop.selected_pos,
            BeamstopPositions.DATA_COLLECTION,
            group=group,
        )
        if detector_distance_mm:
            yield from set_detector_z_position(
                device_composite.detector_motion, detector_distance_mm, group
            )
        yield from set_shutter(
            device_composite.detector_motion, ShutterState.OPEN, group
        )
        yield from plan_to_run

    yield from bpp.contingency_wrapper(
        wrapped_plan(),
        except_plan=lambda e: (yield from bps.stop(device_composite.detector)),  # type: ignore # Fix types in ophyd-async (https://github.com/DiamondLightSource/mx-bluesky/issues/855)
    )
