from __future__ import annotations

import bluesky.plan_stubs as bps
from dodal.devices.aperturescatterguard import (
    ApertureScatterguard,
    ApertureValue,
)
from dodal.devices.backlight import Backlight, InOut
from dodal.devices.detector.detector_motion import DetectorMotion
from dodal.devices.smargon import CombinedMove, Smargon
from dodal.devices.thawer import OnOff, Thawer

from mx_bluesky.common.parameters.components import AperturePolicy
from mx_bluesky.common.parameters.constants import PlanGroupCheckpointConstants
from mx_bluesky.common.utils.log import LOGGER

LOWER_DETECTOR_SHUTTER_AFTER_SCAN = True


def setup_sample_environment(
    aperture_scatterguard: ApertureScatterguard,
    aperture_policy: AperturePolicy,
    backlight: Backlight,
    thawer: Thawer,
    group="setup_senv",
):
    """Move the aperture into required position, move out the backlight so that it
    doesn't cause a shadow on the detector and turn off thawing so it doesn't vibrate
    the pin."""

    yield from bps.abs_set(backlight, InOut.OUT, group=group)

    aperture_value = _rotation_aperture_value_from_policy(aperture_policy)

    yield from move_aperture_if_required(
        aperture_scatterguard, aperture_value, group=group
    )

    yield from bps.abs_set(thawer, OnOff.OFF, group=group)


def prepare_aperture_if_required(
    aperture_scatterguard: ApertureScatterguard,
    aperture_policy: AperturePolicy,
):
    aperture_value = _rotation_aperture_value_from_policy(aperture_policy)
    if aperture_value:
        yield from bps.prepare(
            aperture_scatterguard,
            aperture_value,
            group=PlanGroupCheckpointConstants.PREPARE_APERTURE,
        )


def move_aperture_if_required(
    aperture_scatterguard: ApertureScatterguard,
    aperture_value: ApertureValue | None,
    group="move_aperture",
):
    if not aperture_value:
        previous_aperture_position = yield from bps.rd(aperture_scatterguard)
        assert isinstance(previous_aperture_position, ApertureValue)
        LOGGER.info(
            f"Using previously set aperture position {previous_aperture_position}"
        )

    else:
        LOGGER.info(f"Setting aperture position to {aperture_value}")
        yield from bps.wait(PlanGroupCheckpointConstants.PREPARE_APERTURE)
        yield from bps.abs_set(
            aperture_scatterguard.selected_aperture,
            aperture_value,
            group=group,
        )


def cleanup_sample_environment(
    detector_motion: DetectorMotion,
    group="cleanup_senv",
):
    """Put the detector shutter back down"""

    yield from bps.abs_set(
        detector_motion.shutter,
        int(not LOWER_DETECTOR_SHUTTER_AFTER_SCAN),
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


def move_phi_chi_omega(
    smargon: Smargon,
    phi: float | None = None,
    chi: float | None = None,
    omega: float | None = None,
    wait=False,
    group="move_phi_chi_omega",
):
    """Move the x, y, and z axes of the given smargon to the specified position. All
    axes are optional."""

    LOGGER.info(f"Moving smargon to phi, chi, omega: {(phi, chi, omega)}")
    yield from bps.abs_set(
        smargon, CombinedMove(phi=phi, chi=chi, omega=omega), group=group
    )
    if wait:
        yield from bps.wait(group)


def _rotation_aperture_value_from_policy(
    policy: AperturePolicy,
) -> ApertureValue | None:
    match policy:
        case AperturePolicy.SMALL:
            return ApertureValue.SMALL
        case AperturePolicy.MEDIUM:
            return ApertureValue.MEDIUM
        case AperturePolicy.LARGE | AperturePolicy.AUTO:
            return ApertureValue.LARGE
        case AperturePolicy.CURRENT_POSITION:
            return None
        case _:
            raise ValueError(f"Unsupported aperture policy {policy}")
