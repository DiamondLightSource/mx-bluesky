from __future__ import annotations

from blueapi.core import BlueskyContext
from bluesky.utils import MsgGenerator
from dodal.plans.preprocessors.verify_undulator_gap import (
    verify_undulator_gap_before_run_decorator,
)

from mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan import (
    grid_detect_then_xray_centre,
)
from mx_bluesky.common.external_interaction.callbacks.common.grid_detection_callback import (
    GridParamUpdate,
)
from mx_bluesky.common.parameters.constants import OavConstants
from mx_bluesky.common.parameters.gridscan import GridCommon
from mx_bluesky.common.utils.context import device_composite_from_context
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.hyperion.experiment_plans.hyperion_flyscan_xray_centre_plan import (
    construct_hyperion_specific_features,
)
from mx_bluesky.hyperion.parameters.device_composites import (
    HyperionFlyScanXRayCentreComposite,
    HyperionGridDetectThenXRayCentreComposite,
)
from mx_bluesky.hyperion.parameters.gridscan import (
    GridScanWithEdgeDetect,
    HyperionSpecifiedThreeDGridScan,
)


def create_devices(
    context: BlueskyContext,
) -> HyperionGridDetectThenXRayCentreComposite:
    return device_composite_from_context(
        context, HyperionGridDetectThenXRayCentreComposite
    )


def create_parameters_for_flyscan_xray_centre(
    parameters: GridCommon,
    grid_parameters: GridParamUpdate,
) -> HyperionSpecifiedThreeDGridScan:
    params_json = parameters.model_dump()
    params_json.update(grid_parameters)
    flyscan_xray_centre_parameters = HyperionSpecifiedThreeDGridScan(**params_json)
    LOGGER.info(f"Parameters for FGS: {flyscan_xray_centre_parameters}")
    return flyscan_xray_centre_parameters


def create_hyperion_xrc_composite(
    composite: HyperionGridDetectThenXRayCentreComposite,
):
    return HyperionFlyScanXRayCentreComposite(
        aperture_scatterguard=composite.aperture_scatterguard,
        attenuator=composite.attenuator,
        backlight=composite.backlight,
        eiger=composite.eiger,
        panda_fast_grid_scan=composite.panda_fast_grid_scan,
        flux=composite.flux,
        s4_slit_gaps=composite.s4_slit_gaps,
        smargon=composite.smargon,
        undulator=composite.undulator,
        synchrotron=composite.synchrotron,
        xbpm_feedback=composite.xbpm_feedback,
        zebra=composite.zebra,
        zocalo=composite.zocalo,
        panda=composite.panda,
        zebra_fast_grid_scan=composite.zebra_fast_grid_scan,
        dcm=composite.dcm,
        robot=composite.robot,
        sample_shutter=composite.sample_shutter,
    )


def hyperion_grid_detect_then_xray_centre(
    composite: HyperionGridDetectThenXRayCentreComposite,
    parameters: GridScanWithEdgeDetect,
    oav_config: str = OavConstants.OAV_CONFIG_JSON,
) -> MsgGenerator:
    """
    A plan which combines the collection of snapshots from the OAV and the determination
    of the grid dimensions to use for the following grid scan.
    """

    xrc_composite = create_hyperion_xrc_composite(composite)

    @verify_undulator_gap_before_run_decorator(composite)
    def plan_to_perform():
        yield from grid_detect_then_xray_centre(
            composite=composite,
            parameters=parameters,
            xrc_composite=xrc_composite,
            setup_xrc_params=create_parameters_for_flyscan_xray_centre,
            construct_beamline_specific=construct_hyperion_specific_features,
            oav_config=oav_config,
        )

    yield from plan_to_perform()
