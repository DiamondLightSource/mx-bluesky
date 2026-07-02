from __future__ import annotations

from dodal.common.beamlines.beamline_utils import get_config_client
from dodal.devices.oav.oav_parameters import OAVParameters

from mx_bluesky.common.device_setup_plans.manipulate_sample import move_phi_chi
from mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan import (
    detect_grid_and_do_gridscan,
)
from mx_bluesky.common.experiment_plans.inner_plans.xrc_results_utils import (
    fetch_xrc_results_from_zocalo,
    zocalo_stage_decorator,
)
from mx_bluesky.common.experiment_plans.oav_snapshot_plan import (
    setup_beamline_for_oav,
)
from mx_bluesky.common.experiment_plans.pin_tip_centring_plan import (
    PinTipCentringComposite,
    pin_tip_centre_plan,
)
from mx_bluesky.common.external_interaction.callbacks.grid.grid_detect_and_scan.ispyb_callback import (
    ispyb_activation_wrapper,
)
from mx_bluesky.common.parameters.constants import OavConstants, PlanNameConstants
from mx_bluesky.common.preprocessors.preprocessors import (
    pause_xbpm_feedback_during_collection_at_desired_transmission_decorator,
)
from mx_bluesky.hyperion.experiment_plans.hyperion_flyscan_xray_centre_plan import (
    construct_hyperion_specific_features,
)
from mx_bluesky.hyperion.parameters.constants import CONST
from mx_bluesky.hyperion.parameters.device_composites import (
    HyperionGridDetectThenXRayCentreComposite,
)
from mx_bluesky.hyperion.parameters.gridscan import (
    PinTipCentreThenXrayCentre,
    create_detector_params_with_hyperion_feature_settings,
)


def pin_centre_then_gridscan_plan(
    composite: HyperionGridDetectThenXRayCentreComposite,
    parameters: PinTipCentreThenXrayCentre,
    oav_config_file: str = OavConstants.OAV_CONFIG_JSON,
):
    """Plan that performs a pin tip centre followed by a gridscan to determine the centre of interest."""

    pin_tip_centring_composite = PinTipCentringComposite(
        oav=composite.oav,
        gonio=composite.gonio,
        pin_tip_detection=composite.pin_tip_detection,
    )

    @zocalo_stage_decorator(composite.zocalo)
    def _pin_centre_then_gridscan_and_xrc():
        yield from setup_beamline_for_oav(
            composite.gonio, composite.backlight, composite.aperture_scatterguard
        )

        yield from move_phi_chi(
            composite.gonio,
            parameters.phi_start_deg,
            parameters.chi_start_deg,
            group=CONST.WAIT.READY_FOR_OAV,
        )

        yield from pin_tip_centre_plan(
            pin_tip_centring_composite,
            parameters.tip_offset_um,
            oav_config_file,
        )

        oav_params = OAVParameters(get_config_client(), "xrayCentring", oav_config_file)

        @pause_xbpm_feedback_during_collection_at_desired_transmission_decorator(
            composite,
            parameters.transmission_frac,
            PlanNameConstants.GRIDSCAN_OUTER,
        )
        def _grid_detect_and_gridscan_plan():
            return (
                yield from detect_grid_and_do_gridscan(
                    composite,
                    parameters,
                    parameters,
                    oav_params,
                    lambda: create_detector_params_with_hyperion_feature_settings(
                        parameters
                    ),
                    construct_hyperion_specific_features,
                )
            )

        grid_scan_params = yield from _grid_detect_and_gridscan_plan()
        yield from fetch_xrc_results_from_zocalo(
            composite.zocalo, grid_scan_params, parameters.sample_id
        )

    yield from ispyb_activation_wrapper(_pin_centre_then_gridscan_and_xrc(), parameters)
