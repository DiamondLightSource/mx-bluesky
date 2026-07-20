from __future__ import annotations

from collections.abc import Callable
from functools import partial

from bluesky.utils import MsgGenerator
from dodal.devices.eiger import EigerDetector as ClassicEigerDetector
from ophyd_async.fastcs.eiger import EigerDetector as FastCSEigerDetector

from mx_bluesky.common.device_setup_plans.detector.eiger import (
    create_eiger_beamline_specific,
)
from mx_bluesky.common.device_setup_plans.detector.fastcs_eiger import (
    create_fastcs_eiger_beamline_specific,
)
from mx_bluesky.common.device_setup_plans.gridscan.beamline_specific import (
    BeamlineSpecificFGSFeatures,
    TSetupParameters,
    construct_beamline_specific_fast_gridscan_features,
)
from mx_bluesky.common.device_setup_plans.gridscan.zebra import (
    set_zebra_fgs_3d_params,
    setup_zebra_for_gridscan,
    tidy_up_zebra_after_gridscan,
)
from mx_bluesky.common.parameters.components import DiffractionExperiment
from mx_bluesky.common.parameters.device_composites import TDetector
from mx_bluesky.common.parameters.gridscan import GridScanParams
from mx_bluesky.hyperion.blueapi.composites import (
    HyperionInternalGridDetectThenXRayCentreComposite,
)
from mx_bluesky.hyperion.device_setup_plans.gridscan import (
    panda_tidy,
    panda_triggering_setup,
    set_panda_fgs_params,
)
from mx_bluesky.hyperion.external_interaction.config_server import (
    get_hyperion_feature_settings,
)


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
        setup_trigger_plan = partial(
            panda_triggering_setup, settings=get_hyperion_feature_settings()
        )
        tidy_plan = panda_tidy
        set_flyscan_params_plan = partial(
            set_panda_fgs_params,
            xrc_composite.panda_fast_grid_scan,
            xrc_parameters,
            settings=get_hyperion_feature_settings(),
        )
        fgs_motors = xrc_composite.panda_fast_grid_scan

    else:
        setup_trigger_plan = setup_zebra_for_gridscan
        tidy_plan = tidy_up_zebra_after_gridscan
        set_flyscan_params_plan = partial(
            set_zebra_fgs_3d_params,
            xrc_composite.zebra_fast_grid_scan,
            xrc_parameters,
            set_stub_offsets=get_hyperion_feature_settings().SET_STUB_OFFSETS,
        )
        fgs_motors = xrc_composite.zebra_fast_grid_scan
    if isinstance(xrc_composite.detector, ClassicEigerDetector):
        detector_features = create_eiger_beamline_specific(xrc_composite.detector)
    else:
        assert isinstance(xrc_composite.detector, FastCSEigerDetector), (
            f"Unsupported detector type for detector {xrc_composite.detector}"
        )
        detector_features = create_fastcs_eiger_beamline_specific(
            xrc_composite.detector
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
