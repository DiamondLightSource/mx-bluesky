from __future__ import annotations

import json

import bluesky.preprocessors as bpp
from blueapi.core import BlueskyContext
from bluesky.utils import MsgGenerator
from dodal.devices.eiger import EigerDetector
from dodal.devices.oav.oav_parameters import OAVParameters

from mx_bluesky.common.device_setup_plans.manipulate_sample import move_phi_chi_omega
from mx_bluesky.common.experiment_plans.change_aperture_then_move_plan import (
    change_aperture_then_move_to_xtal,
)
from mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback import (
    ispyb_activation_wrapper,
)
from mx_bluesky.common.parameters.constants import OavConstants
from mx_bluesky.common.utils.context import device_composite_from_context
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.common.xrc_result import XRayCentreEventHandler
from mx_bluesky.hyperion.device_setup_plans.utils import (
    start_preparing_data_collection_then_do_plan,
)
from mx_bluesky.hyperion.experiment_plans.grid_detect_then_xray_centre_plan import (
    GridDetectThenXRayCentreComposite,
    detect_grid_and_do_gridscan,
)
from mx_bluesky.hyperion.experiment_plans.oav_snapshot_plan import (
    setup_beamline_for_OAV,
)
from mx_bluesky.hyperion.experiment_plans.pin_tip_centring_plan import (
    PinTipCentringComposite,
    pin_tip_centre_plan,
)
from mx_bluesky.hyperion.parameters.constants import CONST
from mx_bluesky.hyperion.parameters.gridscan import (
    GridScanWithEdgeDetect,
    PinTipCentreThenXrayCentre,
)


def create_devices(context: BlueskyContext) -> GridDetectThenXRayCentreComposite:
    """
    GridDetectThenXRayCentreComposite contains all the devices we need, reuse that.
    """
    return device_composite_from_context(context, GridDetectThenXRayCentreComposite)


def create_parameters_for_grid_detection(
    pin_centre_parameters: PinTipCentreThenXrayCentre,
) -> GridScanWithEdgeDetect:
    params_json = json.loads(pin_centre_parameters.model_dump_json())
    del params_json["tip_offset_um"]
    grid_detect_and_xray_centre = GridScanWithEdgeDetect(**params_json)
    LOGGER.info(
        f"Parameters for grid detect and xray centre: {grid_detect_and_xray_centre.model_dump_json(indent=2)}"
    )
    return grid_detect_and_xray_centre


def pin_centre_then_flyscan_plan(
    composite: GridDetectThenXRayCentreComposite,
    parameters: PinTipCentreThenXrayCentre,
    oav_config_file: str = OavConstants.OAV_CONFIG_JSON,
):
    """Plan that performs a pin tip centre followed by a flyscan to determine the centres of interest"""

    pin_tip_centring_composite = PinTipCentringComposite(
        oav=composite.oav,
        smargon=composite.smargon,
        backlight=composite.backlight,
        pin_tip_detection=composite.pin_tip_detection,
    )

    def _pin_centre_then_flyscan_plan():
        yield from setup_beamline_for_OAV(
            composite.smargon, composite.backlight, composite.aperture_scatterguard
        )

        yield from move_phi_chi_omega(
            composite.smargon,
            parameters.phi_start_deg,
            parameters.chi_start_deg,
            group=CONST.WAIT.READY_FOR_OAV,
        )

        yield from pin_tip_centre_plan(
            pin_tip_centring_composite,
            parameters.tip_offset_um,
            oav_config_file,
        )

        grid_detect_params = create_parameters_for_grid_detection(parameters)

        oav_params = OAVParameters("xrayCentring", oav_config_file)

        yield from detect_grid_and_do_gridscan(
            composite,
            grid_detect_params,
            oav_params,
        )

    yield from ispyb_activation_wrapper(_pin_centre_then_flyscan_plan(), parameters)


def pin_tip_centre_then_xray_centre(
    composite: GridDetectThenXRayCentreComposite,
    parameters: PinTipCentreThenXrayCentre,
    oav_config_file: str = OavConstants.OAV_CONFIG_JSON,
) -> MsgGenerator:
    """Starts preparing for collection then performs the pin tip centre and xray centre"""
    eiger: EigerDetector = composite.eiger

    eiger.set_detector_parameters(parameters.detector_params)

    flyscan_event_handler = XRayCentreEventHandler()

    @bpp.subs_decorator(flyscan_event_handler)
    def pin_centre_flyscan_then_fetch_results() -> MsgGenerator:
        yield from start_preparing_data_collection_then_do_plan(
            composite.beamstop,
            eiger,
            composite.detector_motion,
            parameters.detector_params.detector_distance,
            pin_centre_then_flyscan_plan(composite, parameters, oav_config_file),
            group=CONST.WAIT.GRID_READY_FOR_DC,
        )

    yield from pin_centre_flyscan_then_fetch_results()
    flyscan_results = flyscan_event_handler.xray_centre_results
    assert flyscan_results, (
        "Flyscan result event not received or no crystal found and exception not raised"
    )
    yield from change_aperture_then_move_to_xtal(
        flyscan_results[0], composite.smargon, composite.aperture_scatterguard
    )
