from __future__ import annotations

import bluesky.plan_stubs as bps
from dodal.devices.aperturescatterguard import (
    ApertureScatterguard,
    ApertureValue,
)
from dodal.devices.backlight import Backlight, BacklightPosition
from dodal.devices.detector.detector_motion import DetectorMotion
from dodal.devices.smargon import Smargon

from mx_bluesky.common.utils.log import LOGGER

LOWER_DETECTOR_SHUTTER_AFTER_SCAN = True


def setup_sample_environment(
    aperture_scatterguard: ApertureScatterguard,
    aperture_position_gda_name: str | None,
    backlight: Backlight,
    group="setup_senv",
):
    """Move the aperture into required position, move out the backlight."""
    aperture_value = (
        None
        if not aperture_position_gda_name
        else ApertureValue(aperture_position_gda_name)
    )
    yield from move_aperture_if_required(
        aperture_scatterguard, aperture_value, group=group
    )
    yield from bps.abs_set(backlight, BacklightPosition.OUT, group=group)


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
    if x_mm is not None:
        yield from bps.abs_set(smargon.x, x_mm, group=group)
    if y_mm is not None:
        yield from bps.abs_set(smargon.y, y_mm, group=group)
    if z_mm is not None:
        yield from bps.abs_set(smargon.z, z_mm, group=group)
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
    if phi is not None:
        yield from bps.abs_set(smargon.phi, phi, group=group)
    if chi is not None:
        yield from bps.abs_set(smargon.chi, chi, group=group)
    if omega is not None:
        yield from bps.abs_set(smargon.omega, omega, group=group)
    if wait:
        yield from bps.wait(group)
