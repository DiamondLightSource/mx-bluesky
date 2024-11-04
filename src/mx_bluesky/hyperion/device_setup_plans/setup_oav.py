from functools import partial

import bluesky.plan_stubs as bps
from dodal.devices.areadetector.plugins.CAM import ColorMode
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.oav.oav_parameters import OAVParameters
from dodal.devices.oav.pin_image_recognition import PinTipDetection

from mx_bluesky.hyperion.parameters.constants import CONST

# Helper function to make sure we set the waiting groups correctly
set_using_group = partial(bps.abs_set, group=CONST.WAIT.READY_FOR_OAV)


def setup_pin_tip_detection_params(
    pin_tip_detect_device: PinTipDetection, parameters: OAVParameters
):
    # select which blur to apply to image
    yield from set_using_group(
        pin_tip_detect_device.preprocess_operation, parameters.preprocess
    )

    # sets length scale for blurring
    yield from set_using_group(
        pin_tip_detect_device.preprocess_ksize, parameters.preprocess_K_size
    )

    # Canny edge detect - lower
    yield from set_using_group(
        pin_tip_detect_device.canny_lower_threshold,
        parameters.canny_edge_lower_threshold,
    )

    # Canny edge detect - upper
    yield from set_using_group(
        pin_tip_detect_device.canny_upper_threshold,
        parameters.canny_edge_upper_threshold,
    )

    # "Close" morphological operation
    yield from set_using_group(
        pin_tip_detect_device.close_ksize, parameters.close_ksize
    )

    # Sample detection direction
    yield from set_using_group(
        pin_tip_detect_device.scan_direction, parameters.direction
    )

    # Minimum height
    yield from set_using_group(
        pin_tip_detect_device.min_tip_height,
        parameters.minimum_height,
    )


def setup_general_oav_params(oav: OAV, parameters: OAVParameters):
    yield from set_using_group(oav.cam.color_mode, ColorMode.RGB1)  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
    yield from set_using_group(oav.cam.acquire_period, parameters.acquire_period)  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
    yield from set_using_group(oav.cam.acquire_time, parameters.exposure)  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
    yield from set_using_group(oav.cam.gain, parameters.gain)  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809

    zoom_level_str = f"{float(parameters.zoom)}x"
    yield from bps.abs_set(
        oav.zoom_controller,  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
        zoom_level_str,
        wait=True,
    )


def pre_centring_setup_oav(
    oav: OAV,
    parameters: OAVParameters,
    pin_tip_detection_device: PinTipDetection,
):
    """
    Setup OAV PVs with required values.
    """
    yield from setup_general_oav_params(oav, parameters)
    yield from setup_pin_tip_detection_params(pin_tip_detection_device, parameters)
    yield from bps.wait(CONST.WAIT.READY_FOR_OAV)
