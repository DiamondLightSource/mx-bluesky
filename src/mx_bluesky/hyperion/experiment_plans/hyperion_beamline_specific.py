from __future__ import annotations

from collections.abc import Callable
from functools import partial

from bluesky.utils import MsgGenerator

from dodal.devices.eiger import EigerDetector as ClassicEigerDetector
from mx_bluesky.common.device_setup_plans.detector.eiger import eiger_pre_arm, eiger_zocalo_hw_read_signals, eiger_arm, \
    eiger_hw_read_during_signals, eiger_disarm
from mx_bluesky.common.device_setup_plans.detector.eiger import eiger_tidy
from mx_bluesky.common.device_setup_plans.gridscan import (
    set_zebra_fgs_3d_params, tidy_up_zebra_after_gridscan, setup_zebra_for_gridscan, )
from mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan import (
    BeamlineSpecificFGSFeatures,
    TSetupParameters,
    construct_beamline_specific_fast_gridscan_features, BeamlineSpecificDetectorFeatures,
)
from mx_bluesky.common.parameters.components import DiffractionExperiment
from mx_bluesky.common.parameters.device_composites import TDetector
from mx_bluesky.common.parameters.gridscan import GridScanParams
from mx_bluesky.hyperion.blueapi.composites import (
    HyperionInternalGridDetectThenXRayCentreComposite,
)
from mx_bluesky.hyperion.device_setup_plans.gridscan import set_panda_fgs_params, panda_triggering_setup, panda_tidy
from mx_bluesky.hyperion.external_interaction.config_server import (
    get_hyperion_feature_settings,
)


class SmargonSpeedError(Exception):
    pass


def construct_hyperion_specific_features(
    xrc_composite: HyperionInternalGridDetectThenXRayCentreComposite[TDetector],
    xrc_parameters: TSetupParameters,
) -> BeamlineSpecificFGSFeatures[
    HyperionInternalGridDetectThenXRayCentreComposite[TDetector], TSetupParameters
]:
    """
    Get all the information needed to do the Hyperion-specific parts of the XRC flyscan.
    """
    signals_to_read_pre_flyscan = [
        xrc_composite.undulator.current_gap,
        xrc_composite.synchrotron.synchrotron_mode,
        xrc_composite.s4_slit_gaps,
        xrc_composite.gonio,
        xrc_composite.dcm.energy_in_keV,
    ]

    signals_to_read_during_collection = [
        xrc_composite.aperture_scatterguard,
        xrc_composite.attenuator.actual_transmission,
        xrc_composite.flux.flux_reading,
        xrc_composite.dcm.energy_in_keV,
        xrc_composite.beamsize,
    ]

    setup_trigger_plan: Callable[
        [
            HyperionInternalGridDetectThenXRayCentreComposite[TDetector],
            DiffractionExperiment,
            GridScanParams,
        ],
        MsgGenerator,
    ]

    if get_hyperion_feature_settings().USE_PANDA_FOR_GRIDSCAN:
        setup_trigger_plan = partial(panda_triggering_setup, settings=get_hyperion_feature_settings())
        tidy_plan = partial(panda_tidy, xrc_composite)
        set_flyscan_params_plan = partial(
            set_panda_fgs_params,
            xrc_composite.panda_fast_grid_scan,
            xrc_parameters,
            settings=get_hyperion_feature_settings()
        )
        fgs_motors = xrc_composite.panda_fast_grid_scan

    else:
        setup_trigger_plan = setup_zebra_for_gridscan
        tidy_plan = partial(
            tidy_up_zebra_after_gridscan,
            xrc_composite.zebra,
            xrc_composite.sample_shutter,
            group="flyscan_zebra_tidy",
            wait=True,
        )
        set_flyscan_params_plan = partial(
            set_zebra_fgs_3d_params,
            xrc_composite.zebra_fast_grid_scan,
            xrc_parameters,
            set_stub_offsets=get_hyperion_feature_settings().SET_STUB_OFFSETS,
        )
        fgs_motors = xrc_composite.zebra_fast_grid_scan
    if isinstance(xrc_composite.detector, ClassicEigerDetector):
        detector_features = BeamlineSpecificDetectorFeatures(
            pre_arm_detector_plan=eiger_pre_arm,
            arm_detector_plan=eiger_arm,
            disarm_detector_plan=eiger_disarm,
            tidy_detector_plan=eiger_tidy,
            detector_zocalo_hw_read_signals=eiger_zocalo_hw_read_signals(xrc_composite.detector),
            detector_hw_read_during_signals=eiger_hw_read_during_signals(xrc_composite.detector),
        )

    features = construct_beamline_specific_fast_gridscan_features(
        detector_features,
        setup_trigger_plan,
        tidy_plan,
        set_flyscan_params_plan,
        fgs_motors,
        signals_to_read_pre_flyscan,
        signals_to_read_during_collection,
        # type: ignore # until https://github.com/DiamondLightSource/mx-bluesky/issues/1076
    )
    return features

