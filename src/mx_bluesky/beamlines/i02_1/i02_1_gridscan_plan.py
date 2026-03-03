from functools import partial

import bluesky.preprocessors as bpp
import pydantic
from bluesky.utils import MsgGenerator
from dodal.beamlines.i02_1 import ZebraFastGridScanTwoD
from dodal.common import inject
from dodal.devices.attenuator.attenuator import ReadOnlyAttenuator
from dodal.devices.common_dcm import DoubleCrystalMonochromatorBase
from dodal.devices.fast_grid_scan import (
    set_fast_grid_scan_params as set_flyscan_params_plan,
)
from dodal.devices.flux import Flux
from dodal.devices.s4_slit_gaps import S4SlitGaps
from dodal.devices.undulator import BaseUndulator
from dodal.devices.zebra.zebra import Zebra

from mx_bluesky.beamlines.i02_1.device_setup_plans.setup_zebra import (
    setup_zebra_for_gridscan,
    tidy_up_zebra_after_gridscan,
)
from mx_bluesky.beamlines.i02_1.parameters.gridscan import SpecifiedTwoDGridScan
from mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan import (
    BeamlineSpecificFGSFeatures,
    common_flyscan_xray_centre,
    construct_beamline_specific_fast_gridscan_features,
)
from mx_bluesky.common.external_interaction.callbacks.common.zocalo_callback import (
    ZocaloCallback,
)
from mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback import (
    GridscanISPyBCallback,
    generate_start_info_from_omega_map,
)
from mx_bluesky.common.external_interaction.callbacks.xray_centre.nexus_callback import (
    GridscanNexusFileCallback,
)
from mx_bluesky.common.parameters.constants import (
    EnvironmentConstants,
    PlanNameConstants,
)
from mx_bluesky.common.parameters.device_composites import (
    FlyScanEssentialDevices,
    GonioWithOmegaType,
)
from mx_bluesky.common.parameters.gridscan import GenericGrid
from mx_bluesky.common.utils.log import LOGGER


def create_gridscan_callbacks() -> tuple[
    GridscanNexusFileCallback, GridscanISPyBCallback
]:
    return (
        GridscanNexusFileCallback(param_type=SpecifiedTwoDGridScan),
        GridscanISPyBCallback(
            param_type=GenericGrid,
            emit=ZocaloCallback(
                PlanNameConstants.DO_FGS,
                EnvironmentConstants.ZOCALO_ENV,
                generate_start_info_from_omega_map,
            ),
        ),
    )


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class FlyScanXRayCentreComposite(FlyScanEssentialDevices[GonioWithOmegaType]):
    """All devices which are directly or indirectly required by this plan"""

    zebra: Zebra
    zebra_fast_grid_scan: ZebraFastGridScanTwoD
    dcm: DoubleCrystalMonochromatorBase
    attenuator: ReadOnlyAttenuator
    flux: Flux
    undulator: BaseUndulator
    s4_slit_gaps: S4SlitGaps


def construct_i02_1_specific_features(
    fgs_composite: FlyScanXRayCentreComposite,
    parameters: SpecifiedTwoDGridScan,
) -> BeamlineSpecificFGSFeatures:
    signals_to_read_pre_flyscan = [
        fgs_composite.synchrotron.synchrotron_mode,
        fgs_composite.gonio,
        fgs_composite.dcm.energy_in_keV,
        fgs_composite.undulator.current_gap,
        fgs_composite.s4_slit_gaps,
    ]

    signals_to_read_during_collection = [
        fgs_composite.attenuator.actual_transmission,
        fgs_composite.flux.flux_reading,
        fgs_composite.dcm.energy_in_keV,
        fgs_composite.eiger.bit_depth,
        fgs_composite.eiger.cam.roi_mode,
        fgs_composite.eiger.ispyb_detector_id,
    ]

    return construct_beamline_specific_fast_gridscan_features(
        partial(_zebra_triggering_setup),
        partial(_tidy_plan, fgs_composite, group="flyscan_zebra_tidy", wait=True),
        partial(
            set_flyscan_params_plan,
            fgs_composite.zebra_fast_grid_scan,
            parameters.fast_gridscan_params,
        ),
        fgs_composite.zebra_fast_grid_scan,
        signals_to_read_pre_flyscan,
        signals_to_read_during_collection,  # type: ignore # See : https://github.com/bluesky/bluesky/issues/1809
    )


def _zebra_triggering_setup(fgs_composite: FlyScanXRayCentreComposite, _):
    yield from setup_zebra_for_gridscan(fgs_composite.zebra)


def _tidy_plan(
    fgs_composite: FlyScanXRayCentreComposite, group, wait=True
) -> MsgGenerator:
    LOGGER.info("Tidying up Zebra")
    yield from tidy_up_zebra_after_gridscan(fgs_composite.zebra)


def i02_1_gridscan_plan(
    parameters: SpecifiedTwoDGridScan,
    composite: FlyScanXRayCentreComposite = inject(""),
) -> MsgGenerator:
    """BlueAPI entry point for i02-1 grid scans"""

    beamline_specific = construct_i02_1_specific_features(composite, parameters)
    callbacks = create_gridscan_callbacks()

    @bpp.subs_decorator(callbacks)
    def decorated_flyscan_plan():
        yield from common_flyscan_xray_centre(composite, parameters, beamline_specific)

    yield from decorated_flyscan_plan()
