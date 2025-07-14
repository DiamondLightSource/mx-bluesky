from __future__ import annotations

from blueapi.core import BlueskyContext
from bluesky.utils import MsgGenerator
from dodal.plans.preprocessors.verify_undulator_gap import (
    verify_undulator_gap_before_run_decorator,
)

from mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan import (
    grid_detect_then_xray_centre,
)
from mx_bluesky.common.parameters.constants import OavConstants, PlanNameConstants
from mx_bluesky.common.preprocessors.preprocessors import (
    transmission_and_xbpm_feedback_for_collection_decorator,
)
from mx_bluesky.common.utils.context import device_composite_from_context
from mx_bluesky.hyperion.experiment_plans.hyperion_flyscan_xray_centre_plan import (
    construct_hyperion_specific_features,
)
from mx_bluesky.hyperion.parameters.device_composites import (
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


def hyperion_grid_detect_then_xray_centre(
    composite: HyperionGridDetectThenXRayCentreComposite,
    parameters: GridScanWithEdgeDetect,
    oav_config: str = OavConstants.OAV_CONFIG_JSON,
) -> MsgGenerator:
    """
    A plan which combines the collection of snapshots from the OAV and the determination
    of the grid dimensions to use for the following grid scan.
    """

    @verify_undulator_gap_before_run_decorator(composite)
    @transmission_and_xbpm_feedback_for_collection_decorator(
        composite, parameters.transmission_frac, PlanNameConstants.GRIDSCAN_OUTER
    )
    def plan_to_perform():
        yield from grid_detect_then_xray_centre(
            composite=composite,
            parameters=parameters,
            xrc_params_type=HyperionSpecifiedThreeDGridScan,
            construct_beamline_specific=construct_hyperion_specific_features,
            oav_config=oav_config,
        )

    yield from plan_to_perform()
