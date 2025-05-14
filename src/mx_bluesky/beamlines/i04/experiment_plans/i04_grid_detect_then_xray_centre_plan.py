from __future__ import annotations

from functools import partial

import bluesky.preprocessors as bpp
from blueapi.core import BlueskyContext
from bluesky.utils import MsgGenerator
from dodal.devices.aperturescatterguard import ApertureScatterguard
from dodal.devices.backlight import Backlight
from dodal.devices.detector.detector_motion import DetectorMotion
from dodal.devices.fast_grid_scan import (
    set_fast_grid_scan_params,
)
from dodal.devices.smargon import Smargon
from dodal.plans.preprocessors.verify_undulator_gap import (
    verify_undulator_gap_before_run_decorator,
)

from mx_bluesky.beamlines.i04.parameters.device_composites import (
    I04FlyScanXRayCentreComposite,
)
from mx_bluesky.common.device_setup_plans.manipulate_sample import (
    cleanup_sample_environment,
)
from mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan import (
    BeamlineSpecificFGSFeatures,
    construct_beamline_specific_FGS_features,
)
from mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan import (
    grid_detect_then_xray_centre,
)
from mx_bluesky.common.experiment_plans.oav_snapshot_plan import (
    setup_beamline_for_OAV,
)
from mx_bluesky.common.external_interaction.callbacks.common.zocalo_callback import (
    ZocaloCallback,
)
from mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback import (
    GridscanISPyBCallback,
)
from mx_bluesky.common.external_interaction.callbacks.xray_centre.nexus_callback import (
    GridscanNexusFileCallback,
)
from mx_bluesky.common.parameters.constants import (
    EnvironmentConstants,
    OavConstants,
    PlanNameConstants,
)
from mx_bluesky.common.parameters.device_composites import (
    GridDetectThenXRayCentreComposite,
)
from mx_bluesky.common.parameters.gridscan import GridCommon, SpecifiedThreeDGridScan
from mx_bluesky.common.utils.context import device_composite_from_context
from mx_bluesky.hyperion.experiment_plans.hyperion_flyscan_xray_centre_plan import (
    _generic_tidy,
    _zebra_triggering_setup,
)


def create_devices(
    context: BlueskyContext,
) -> GridDetectThenXRayCentreComposite:
    return device_composite_from_context(context, GridDetectThenXRayCentreComposite)


def i04_grid_detect_then_xray_centre(
    composite: GridDetectThenXRayCentreComposite,
    parameters: GridCommon,
    oav_config: str = OavConstants.OAV_CONFIG_JSON,
    udc: bool = False,
) -> MsgGenerator:
    """
    An plan which combines the collection of snapshots from the OAV and the determination
    of the grid dimensions to use for the following grid scan.
    """
    yield from setup_beamline_for_OAV(
        composite.smargon, composite.backlight, composite.aperture_scatterguard
    )

    callbacks = create_gridscan_callbacks()

    @bpp.subs_decorator(callbacks)
    @verify_undulator_gap_before_run_decorator(composite)
    def grid_detect_then_xray_centre_with_callbacks():
        yield from grid_detect_then_xray_centre(
            composite=composite,
            parameters=parameters,
            xrc_params_type=SpecifiedThreeDGridScan,
            construct_beamline_specific=construct_i04_specific_features,
            oav_config=oav_config,
        )

    yield from grid_detect_then_xray_centre_with_callbacks()

    if not udc:
        yield from get_ready_for_oav_and_close_shutter(
            composite.smargon,
            composite.backlight,
            composite.aperture_scatterguard,
            composite.detector_motion,
        )


def get_ready_for_oav_and_close_shutter(
    smargon: Smargon,
    backlight: Backlight,
    aperture_scatterguard: ApertureScatterguard,
    detector_motion: DetectorMotion,
):
    yield from setup_beamline_for_OAV(smargon, backlight, aperture_scatterguard)
    yield from cleanup_sample_environment(detector_motion)


def create_gridscan_callbacks() -> tuple[
    GridscanNexusFileCallback, GridscanISPyBCallback
]:
    return (
        GridscanNexusFileCallback(param_type=SpecifiedThreeDGridScan),
        GridscanISPyBCallback(
            param_type=GridCommon,
            emit=ZocaloCallback(
                PlanNameConstants.DO_FGS, EnvironmentConstants.ZOCALO_ENV
            ),
        ),
    )


def construct_i04_specific_features(
    xrc_composite: I04FlyScanXRayCentreComposite,
    xrc_parameters: SpecifiedThreeDGridScan,
) -> BeamlineSpecificFGSFeatures:
    """
    Get all the information needed to do the i04 XRC flyscan.
    """
    signals_to_read_pre_flyscan = [
        xrc_composite.undulator.current_gap,
        xrc_composite.synchrotron.synchrotron_mode,
        xrc_composite.s4_slit_gaps.xgap,
        xrc_composite.s4_slit_gaps.ygap,
        xrc_composite.smargon.x,
        xrc_composite.smargon.y,
        xrc_composite.smargon.z,
        xrc_composite.dcm.energy_in_kev,
    ]

    signals_to_read_during_collection = [
        xrc_composite.aperture_scatterguard,
        xrc_composite.attenuator.actual_transmission,
        xrc_composite.flux.flux_reading,
        xrc_composite.dcm.energy_in_kev,
        xrc_composite.eiger.bit_depth,
    ]

    setup_trigger_plan = _zebra_triggering_setup
    tidy_plan = partial(_generic_tidy, group="flyscan_zebra_tidy", wait=True)
    set_flyscan_params_plan = partial(
        set_fast_grid_scan_params,
        xrc_composite.zebra_fast_grid_scan,
        xrc_parameters.FGS_params,
    )
    fgs_motors = xrc_composite.zebra_fast_grid_scan
    return construct_beamline_specific_FGS_features(
        setup_trigger_plan,
        tidy_plan,
        set_flyscan_params_plan,
        fgs_motors,
        signals_to_read_pre_flyscan,
        signals_to_read_during_collection,
        get_xrc_results_from_zocalo=True,
    )
