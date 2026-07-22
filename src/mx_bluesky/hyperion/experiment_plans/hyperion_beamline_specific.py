from __future__ import annotations

from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any

import bluesky.plan_stubs as bps
from bluesky.protocols import Readable
from bluesky.utils import MsgGenerator
from dodal.devices.eiger import EigerDetector

from mx_bluesky.common.device_setup_plans.eiger import tidy_eiger
from mx_bluesky.common.device_setup_plans.gridscan import (
    panda_fast_gridscan_params,
    set_panda_fgs_params,
    set_zebra_fgs_3d_params,
)
from mx_bluesky.common.device_setup_plans.setup_zebra_and_shutter import (
    setup_zebra_for_gridscan,
    tidy_up_zebra_after_gridscan,
)
from mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan import (
    BeamlineSpecificFGSFeatures,
    TSetupParameters,
    construct_beamline_specific_fast_gridscan_features,
)
from mx_bluesky.common.parameters.components import DiffractionExperiment
from mx_bluesky.common.parameters.device_composites import TDetector
from mx_bluesky.common.parameters.gridscan import GridScanParams
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.hyperion.blueapi.composites import (
    HyperionInternalGridDetectThenXRayCentreComposite,
)
from mx_bluesky.hyperion.device_setup_plans.setup_panda import (
    disarm_panda_for_gridscan,
    set_panda_directory,
    setup_panda_for_flyscan,
)
from mx_bluesky.hyperion.device_setup_plans.setup_zebra import (
    setup_zebra_for_panda_flyscan,
)
from mx_bluesky.hyperion.external_interaction.config_server import (
    get_hyperion_feature_settings,
)


class SmargonSpeedError(Exception):
    pass


def construct_hyperion_specific_features(
    xrc_composite: HyperionInternalGridDetectThenXRayCentreComposite[TDetector],
    xrc_parameters: TSetupParameters,
    grid_scan_params: GridScanParams,
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

    signals_to_read_during_collection += _detector_signals_to_read_during_collection(
        xrc_composite.detector
    )

    setup_trigger_plan: Callable[
        [
            HyperionInternalGridDetectThenXRayCentreComposite[TDetector],
            DiffractionExperiment,
            GridScanParams,
        ],
        MsgGenerator,
    ]

    if get_hyperion_feature_settings().USE_PANDA_FOR_GRIDSCAN:
        setup_trigger_plan = _panda_triggering_setup
        tidy_plan = partial(_panda_tidy, xrc_composite)
        set_flyscan_params_plan = partial(
            set_panda_fgs_params,
            xrc_composite.panda_fast_grid_scan,
            xrc_parameters,
            set_stub_offsets=get_hyperion_feature_settings().SET_STUB_OFFSETS,
            run_up_distance_mm=get_hyperion_feature_settings().PANDA_RUNUP_DISTANCE_MM,
        )
        fgs_motors = xrc_composite.panda_fast_grid_scan

    else:
        setup_trigger_plan = _setup_zebra_for_gridscan
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
    features = construct_beamline_specific_fast_gridscan_features(
        setup_trigger_plan,
        tidy_plan,
        tidy_eiger,
        set_flyscan_params_plan,
        fgs_motors,
        signals_to_read_pre_flyscan,
        signals_to_read_during_collection,
        # type: ignore # until https://github.com/DiamondLightSource/mx-bluesky/issues/1076
    )
    return features


def _setup_zebra_for_gridscan(
    composite: HyperionInternalGridDetectThenXRayCentreComposite, _, __
):
    yield from setup_zebra_for_gridscan(composite)


def _detector_signals_to_read_during_collection(detector: Any) -> list[Readable]:
    match detector:
        case EigerDetector():
            return [  # type: ignore
                detector.bit_depth,
                detector.cam.roi_mode,
                detector.ispyb_detector_id,
            ]
        case _:
            raise ValueError(f"Unsupported detector type {type(detector)}")


def _panda_tidy(xrc_composite: HyperionInternalGridDetectThenXRayCentreComposite):
    group = "panda_flyscan_tidy"
    LOGGER.info("Disabling panda blocks")
    yield from disarm_panda_for_gridscan(xrc_composite.panda, group)
    yield from tidy_up_zebra_after_gridscan(
        xrc_composite.zebra, xrc_composite.sample_shutter, group=group, wait=False
    )
    yield from bps.unstage(xrc_composite.panda, group=group)
    yield from bps.wait(group, timeout=10)


def _panda_triggering_setup(
    xrc_composite: HyperionInternalGridDetectThenXRayCentreComposite,
    parameters: DiffractionExperiment,
    grid_scan_parameters: GridScanParams,
) -> MsgGenerator:
    LOGGER.info("Setting up Panda for flyscan")

    run_up_distance_mm = yield from bps.rd(
        xrc_composite.panda_fast_grid_scan.run_up_distance_mm
    )

    detector_deadtime_s = 1e-4  # This value was empirically found to be safer than the documented deadtime in the Eiger manual

    time_between_x_steps_ms = (detector_deadtime_s + parameters.exposure_time_s) * 1e3

    smargon_speed_limit_mm_per_s = yield from bps.rd(xrc_composite.gonio.x.max_velocity)

    panda_params = panda_fast_gridscan_params(parameters, grid_scan_parameters)
    sample_velocity_mm_per_s = (
        panda_params.x_step_size_mm * 1e3 / time_between_x_steps_ms
    )
    if sample_velocity_mm_per_s > smargon_speed_limit_mm_per_s:
        raise SmargonSpeedError(
            f"Smargon speed was calculated from x step size\
            {panda_params.x_step_size_mm}mm and\
            time_between_x_steps_ms {time_between_x_steps_ms} as\
            {sample_velocity_mm_per_s}mm/s. The smargon's speed limit is\
            {smargon_speed_limit_mm_per_s}mm/s."
        )
    else:
        LOGGER.info(
            f"Panda grid scan: Smargon speed set to {sample_velocity_mm_per_s} mm/s"
            f" and using a run-up distance of {run_up_distance_mm}"
        )

    yield from bps.mv(
        xrc_composite.panda_fast_grid_scan.time_between_x_steps_ms,
        time_between_x_steps_ms,
    )

    directory_provider_root = Path(parameters.storage_directory)
    yield from set_panda_directory(directory_provider_root)

    yield from setup_panda_for_flyscan(
        xrc_composite.panda,
        panda_params,
        xrc_composite.gonio,
        parameters.exposure_time_s,
        time_between_x_steps_ms,
        sample_velocity_mm_per_s,
    )

    LOGGER.info("Setting up Zebra for panda flyscan")
    yield from setup_zebra_for_panda_flyscan(
        xrc_composite.zebra, xrc_composite.sample_shutter, wait=True
    )
