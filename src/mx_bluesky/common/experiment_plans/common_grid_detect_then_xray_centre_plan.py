from __future__ import annotations

from pathlib import Path
from typing import Protocol, TypeVar

from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp
from bluesky.utils import MsgGenerator
from dodal.common.beamlines.beamline_utils import get_config_client
from dodal.devices.aperturescatterguard import ApertureScatterguard, ApertureValue
from dodal.devices.backlight import InOut
from dodal.devices.eiger import EigerDetector
from dodal.devices.oav.oav_parameters import OAVParameters

from mx_bluesky.common.device_setup_plans.manipulate_sample import (
    move_aperture_if_required,
)
from mx_bluesky.common.device_setup_plans.utils import (
    start_preparing_data_collection_then_do_plan,
)
from mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan import (
    BeamlineSpecificFGSFeatures,
    common_flyscan_xray_centre,
)
from mx_bluesky.common.experiment_plans.oav_grid_detection_plan import (
    OavGridDetectionComposite,
    grid_detection_plan,
)
from mx_bluesky.common.experiment_plans.oav_snapshot_plan import (
    setup_beamline_for_oav,
)
from mx_bluesky.common.external_interaction.callbacks.common.grid_detection_callback import (
    GridDetectionCallback,
    GridParamUpdate,
)
from mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback import (
    ispyb_activation_wrapper,
)
from mx_bluesky.common.parameters.components import AperturePolicy
from mx_bluesky.common.parameters.constants import (
    OavConstants,
    PlanGroupCheckpointConstants,
)
from mx_bluesky.common.parameters.device_composites import (
    FlyScanEssentialDevices,
    GridDetectThenXRayCentreComposite,
)
from mx_bluesky.common.parameters.gridscan import GridCommon, SpecifiedThreeDGridScan
from mx_bluesky.common.utils.log import LOGGER

TFlyScanEssentialDevices = TypeVar(
    "TFlyScanEssentialDevices", bound=FlyScanEssentialDevices, contravariant=True
)
TSpecifiedThreeDGridScan = TypeVar(
    "TSpecifiedThreeDGridScan", bound=SpecifiedThreeDGridScan, contravariant=True
)


def grid_detect_then_xray_centre(
    composite: GridDetectThenXRayCentreComposite,
    parameters: GridCommon,
    xrc_params_type: type[SpecifiedThreeDGridScan],
    construct_beamline_specific: ConstructBeamlineSpecificFeatures,
    oav_config: str = OavConstants.OAV_CONFIG_JSON,
) -> MsgGenerator:
    """
    A plan which combines the collection of snapshots from the OAV and the determination
    of the grid dimensions to use for the following grid scan.
    """

    eiger: EigerDetector = composite.eiger

    eiger.set_detector_parameters(parameters.detector_params)

    oav_params = OAVParameters(get_config_client(), "xrayCentring", oav_config)

    def plan_to_perform():
        yield from ispyb_activation_wrapper(
            detect_grid_and_do_gridscan(
                composite,
                parameters,
                oav_params,
                xrc_params_type,
                construct_beamline_specific,
            ),
            parameters,
        )

    yield from start_preparing_data_collection_then_do_plan(
        composite.beamstop,
        eiger,
        composite.detector_motion,
        parameters.detector_params.detector_distance,
        plan_to_perform(),
        group=PlanGroupCheckpointConstants.GRID_READY_FOR_DC,
    )


# This function should be private but is currently called by Hyperion, see https://github.com/DiamondLightSource/mx-bluesky/issues/1148
def detect_grid_and_do_gridscan(
    composite: GridDetectThenXRayCentreComposite,
    parameters: GridCommon,
    oav_params: OAVParameters,
    xrc_params_type: type[SpecifiedThreeDGridScan],
    construct_beamline_specific: ConstructBeamlineSpecificFeatures,
):
    snapshot_template = f"{parameters.detector_params.prefix}_{parameters.detector_params.run_number}_{{angle}}"

    grid_params_callback = GridDetectionCallback()

    # Determine the aperture value before moving it for the OAV in case aperture_policy is CURRENT_POSITION
    aperture_value = yield from _xrc_aperture_value_from_policy(
        parameters.selected_aperture, composite.aperture_scatterguard
    )

    yield from setup_beamline_for_oav(
        composite.gonio,
        composite.backlight,
        composite.aperture_scatterguard,
        wait=True,
    )

    @bpp.subs_decorator([grid_params_callback])
    def run_grid_detection_plan(
        oav_params,
        snapshot_template,
        snapshot_dir: Path,
    ):
        grid_detect_composite = OavGridDetectionComposite(
            backlight=composite.backlight,
            oav=composite.oav,
            gonio=composite.gonio,
            pin_tip_detection=composite.pin_tip_detection,
        )

        yield from grid_detection_plan(
            grid_detect_composite,
            oav_params,
            snapshot_template,
            str(snapshot_dir),
            parameters.grid_width_um,
            parameters.box_size_um,
        )

    # Start moving the aperture/scatterguard into position without moving it in
    yield from bps.prepare(
        composite.aperture_scatterguard,
        aperture_value,
        group=PlanGroupCheckpointConstants.PREPARE_APERTURE,
    )

    yield from run_grid_detection_plan(
        oav_params,
        snapshot_template,
        parameters.snapshot_directory,
    )

    yield from bps.abs_set(
        composite.backlight,
        InOut.OUT,
        group=PlanGroupCheckpointConstants.GRID_READY_FOR_DC,
    )

    yield from bps.wait(PlanGroupCheckpointConstants.PREPARE_APERTURE)
    yield from move_aperture_if_required(
        composite.aperture_scatterguard,
        aperture_value,
        group=PlanGroupCheckpointConstants.GRID_READY_FOR_DC,
    )
    xrc_params = create_parameters_for_flyscan_xray_centre(
        parameters, grid_params_callback.get_grid_parameters(), xrc_params_type
    )
    parameters.set_specified_grid_params(xrc_params)
    beamline_specific = construct_beamline_specific(composite, xrc_params)

    yield from common_flyscan_xray_centre(composite, xrc_params, beamline_specific)


class ConstructBeamlineSpecificFeatures(
    Protocol[TFlyScanEssentialDevices, TSpecifiedThreeDGridScan]
):
    def __call__(
        self,
        xrc_composite: TFlyScanEssentialDevices,
        xrc_parameters: TSpecifiedThreeDGridScan,
    ) -> BeamlineSpecificFGSFeatures: ...


def create_parameters_for_flyscan_xray_centre(
    parameters: GridCommon,
    grid_parameters: GridParamUpdate,
    xrc_params_type: type[SpecifiedThreeDGridScan],
) -> SpecifiedThreeDGridScan:
    params_json = parameters.model_dump()
    params_json.update(grid_parameters)
    flyscan_xray_centre_parameters = xrc_params_type(**params_json)
    LOGGER.info(f"Parameters for FGS: {flyscan_xray_centre_parameters}")
    return flyscan_xray_centre_parameters


def _xrc_aperture_value_from_policy(
    policy: AperturePolicy, aperture_scatterguard: ApertureScatterguard
) -> MsgGenerator[ApertureValue | None]:
    match policy:
        case AperturePolicy.SMALL | AperturePolicy.AUTO:
            return ApertureValue.SMALL
        case AperturePolicy.MEDIUM:
            return ApertureValue.MEDIUM
        case AperturePolicy.LARGE:
            return ApertureValue.LARGE
        case AperturePolicy.CURRENT_POSITION:
            previous_aperture_position = yield from bps.rd(aperture_scatterguard)
            assert isinstance(previous_aperture_position, ApertureValue)
            LOGGER.info(
                f"Using previously set aperture position {previous_aperture_position}"
            )
            return previous_aperture_position
        case _:
            raise ValueError(f"Unsupported aperture policy {policy}")
