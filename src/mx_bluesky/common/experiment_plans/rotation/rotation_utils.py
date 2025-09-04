from __future__ import annotations

import dataclasses

from dodal.devices.zebra.zebra import RotationDirection
from dodal.utils import get_beamline_name

from mx_bluesky.common.parameters.constants import RotationParamConstants
from mx_bluesky.common.parameters.rotation import SingleRotationScan
from mx_bluesky.common.utils.log import LOGGER

DEFAULT_DIRECTION = RotationDirection.NEGATIVE
DEFAULT_MAX_VELOCITY = 120
# Use a slightly larger time to acceleration than EPICS as it's better to be cautious
ACCELERATION_MARGIN = 1.5


@dataclasses.dataclass
class RotationMotionProfile:
    start_scan_deg: float
    start_motion_deg: float
    scan_width_deg: float
    shutter_time_s: float
    direction: RotationDirection
    speed_for_rotation_deg_s: float
    acceleration_offset_deg: float
    shutter_opening_deg: float
    total_exposure_s: float
    distance_to_move_deg: float
    max_velocity_deg_s: float


def calculate_motion_profile(
    params: SingleRotationScan,
    motor_time_to_speed_s: float,
    max_velocity_deg_s: float,
) -> RotationMotionProfile:
    """Calculates the various numbers needed for motions in the rotation scan.
    Rotates through "scan width" plus twice an "offset" to take into account
    acceleration at the start and deceleration at the end, plus the number of extra
    degrees of rotation needed to make sure the fast shutter has fully opened before the
    detector trigger is sent.
    See https://github.com/DiamondLightSource/hyperion/wiki/rotation-scan-geometry
    for a simple pictorial explanation."""

    assert params.rotation_increment_deg > 0

    direction = params.rotation_direction
    start_scan_deg = params.omega_start_deg

    if RotationParamConstants.OMEGA_FLIP:
        # If omega_flip is True then the motor omega axis is inverted with respect to the
        # coordinate system.
        start_scan_deg = -start_scan_deg
        direction = (
            direction.POSITIVE
            if direction == direction.NEGATIVE
            else direction.NEGATIVE
        )

    num_images = params.num_images
    shutter_time_s = params.shutter_opening_time_s
    image_width_deg = params.rotation_increment_deg
    exposure_time_s = params.exposure_time_s
    motor_time_to_speed_s *= ACCELERATION_MARGIN

    LOGGER.info("Calculating rotation scan motion profile:")
    LOGGER.info(
        f"{num_images=}, {shutter_time_s=}, {image_width_deg=}, {exposure_time_s=}, {direction=}"
    )

    scan_width_deg = num_images * params.rotation_increment_deg
    LOGGER.info(f"{scan_width_deg=} = {num_images=} * {params.rotation_increment_deg=}")

    speed_for_rotation_deg_s = image_width_deg / exposure_time_s
    LOGGER.info("speed_for_rotation_deg_s = image_width_deg / exposure_time_s")
    LOGGER.info(
        f"{speed_for_rotation_deg_s=} = {image_width_deg=} / {exposure_time_s=}"
    )

    acceleration_offset_deg = motor_time_to_speed_s * speed_for_rotation_deg_s
    LOGGER.info(
        f"{acceleration_offset_deg=} = {motor_time_to_speed_s=} * {speed_for_rotation_deg_s=}"
    )

    start_motion_deg = start_scan_deg - (acceleration_offset_deg * direction.multiplier)
    LOGGER.info(
        f"{start_motion_deg=} = {start_scan_deg=} - ({acceleration_offset_deg=} * {direction.multiplier=})"
    )

    shutter_opening_deg = speed_for_rotation_deg_s * shutter_time_s
    LOGGER.info(
        f"{shutter_opening_deg=} = {speed_for_rotation_deg_s=} * {shutter_time_s=}"
    )

    shutter_opening_deg = speed_for_rotation_deg_s * shutter_time_s
    LOGGER.info(
        f"{shutter_opening_deg=} = {speed_for_rotation_deg_s=} * {shutter_time_s=}"
    )

    total_exposure_s = num_images * exposure_time_s
    LOGGER.info(f"{total_exposure_s=} = {num_images=} * {exposure_time_s=}")

    distance_to_move_deg = (
        scan_width_deg + shutter_opening_deg + acceleration_offset_deg * 2
    ) * direction.multiplier
    LOGGER.info(
        f"{distance_to_move_deg=} = ({scan_width_deg=} + {shutter_opening_deg=} + {acceleration_offset_deg=} * 2) * {direction=})"
    )

    # See https://github.com/DiamondLightSource/mx-bluesky/issues/1224
    if get_beamline_name("i03") == "i24":
        acceleration_offset_deg = 10

    return RotationMotionProfile(
        start_scan_deg=start_scan_deg,
        start_motion_deg=start_motion_deg,
        scan_width_deg=scan_width_deg,
        shutter_time_s=shutter_time_s,
        direction=direction,
        speed_for_rotation_deg_s=speed_for_rotation_deg_s,
        acceleration_offset_deg=acceleration_offset_deg,
        shutter_opening_deg=shutter_opening_deg,
        total_exposure_s=total_exposure_s,
        distance_to_move_deg=distance_to_move_deg,
        max_velocity_deg_s=max_velocity_deg_s,
    )
