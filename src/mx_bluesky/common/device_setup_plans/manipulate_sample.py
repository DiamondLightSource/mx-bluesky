from __future__ import annotations

from typing import TypeVar

import bluesky.plan_stubs as bps
from dodal.devices.backlight import Backlight, InOut
from dodal.devices.detector.detector_motion import DetectorMotion, ShutterState
from dodal.devices.smargon import CombinedMove, Smargon
from dodal.devices.thawer import OnOff, Thawer

from mx_bluesky.common.device_setup_plans.beamsize.beamsize import (
    BeamSizePlans,
    TBeamSizeValue,
)
from mx_bluesky.common.parameters.constants import PlanGroupCheckpointConstants
from mx_bluesky.common.utils.log import LOGGER

LOWER_DETECTOR_SHUTTER_AFTER_SCAN = True

T = TypeVar("T")


def setup_sample_environment(
    beamsize_devices: T,
    beamsize_device_plans: BeamSizePlans[T, TBeamSizeValue],
    aperture_value: TBeamSizeValue,
    backlight: Backlight,
    thawer: Thawer,
    group="setup_senv",
):
    """Move the aperture into required position, move out the backlight so that it
    doesn't cause a shadow on the detector and turn off thawing so it doesn't vibrate
    the pin."""

    yield from bps.abs_set(backlight, InOut.OUT, group=group)

    yield from bps.wait(PlanGroupCheckpointConstants.PREPARE_APERTURE)
    yield from beamsize_device_plans.perform_beam_size(
        beamsize_devices, aperture_value, group
    )
    yield from bps.abs_set(thawer, OnOff.OFF, group=group)


def cleanup_sample_environment(
    detector_motion: DetectorMotion,
    group="cleanup_senv",
):
    """Put the detector shutter back down"""

    yield from bps.abs_set(
        detector_motion.shutter,
        ShutterState.CLOSED if LOWER_DETECTOR_SHUTTER_AFTER_SCAN else ShutterState.OPEN,
        group=group,
    )


def move_x_y_z(
    smargon: Smargon,
    x_mm: float | None = None,
    y_mm: float | None = None,
    z_mm: float | None = None,
    wait=False,
    group="move_x_y_z",
):
    """Move the x, y, and z axes of the given smargon to the specified position. All
    axes are optional."""

    LOGGER.info(f"Moving smargon to x, y, z: {(x_mm, y_mm, z_mm)}")
    yield from bps.abs_set(smargon, CombinedMove(x=x_mm, y=y_mm, z=z_mm), group=group)
    if wait:
        yield from bps.wait(group)


def move_phi_chi(
    smargon: Smargon,
    phi: float | None = None,
    chi: float | None = None,
    wait=False,
    group="move_phi_chi_omega",
):
    """Move the phi, chi of the given smargon to the specified position. All
    axes are optional."""

    LOGGER.info(f"Moving smargon to phi, chi: {(phi, chi)}")
    yield from bps.abs_set(smargon, CombinedMove(phi=phi, chi=chi), group=group)
    if wait:
        yield from bps.wait(group)
