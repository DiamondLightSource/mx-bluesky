from functools import partial
from pathlib import Path

import bluesky.preprocessors as bpp
import pydantic
from bluesky.utils import MsgGenerator
from dodal.beamlines.i02_1 import ZebraFastGridScanTwoD
from dodal.common import inject
from dodal.devices.attenuator.attenuator import ReadOnlyAttenuator
from dodal.devices.beamlines.i02_1.flux import Flux
from dodal.devices.common_dcm import DoubleCrystalMonochromatorBase
from dodal.devices.fast_grid_scan import (
    set_fast_grid_scan_params as set_flyscan_params_plan,
)
from dodal.devices.slits import Slits
from dodal.devices.undulator import BaseUndulator
from dodal.devices.zebra.zebra import Zebra
from pydantic import BaseModel
from pydantic_extra_types.semantic_version import SemanticVersion
from semver import Version

from mx_bluesky.beamlines.i02_1.composites import I02_1FgsParams
from mx_bluesky.beamlines.i02_1.device_setup_plans.setup_zebra import (
    setup_zebra_for_gridscan,
    tidy_up_zebra_after_gridscan,
)
from mx_bluesky.beamlines.i02_1.external_interaction.callbacks.gridscan.ispyb_callback import (
    GridscanISPyBCallback,
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
from mx_bluesky.common.external_interaction.callbacks.grid.grid_detect_and_scan.nexus_callback import (
    GridscanNexusFileCallback,
)
from mx_bluesky.common.external_interaction.callbacks.grid.gridscan.ispyb_callback import (
    ispyb_activation_decorator,
)
from mx_bluesky.common.external_interaction.callbacks.grid.utils import (
    generate_start_info_from_num_grids,
)
from mx_bluesky.common.parameters.components import (
    IspybExperimentType,
    get_param_version,
)
from mx_bluesky.common.parameters.constants import (
    EnvironmentConstants,
    PlanNameConstants,
)
from mx_bluesky.common.parameters.device_composites import (
    FlyScanEssentialDevices,
    GonioWithOmegaType,
)
from mx_bluesky.common.parameters.gridscan import PositiveFloat
from mx_bluesky.common.utils.log import LOGGER


def create_gridscan_callbacks(
    params: I02_1FgsParams,
) -> tuple[GridscanNexusFileCallback, GridscanISPyBCallback]:
    return (
        GridscanNexusFileCallback(param_type=SpecifiedTwoDGridScan),
        GridscanISPyBCallback(
            param_type=I02_1FgsParams,
            emit=ZocaloCallback(
                PlanNameConstants.DO_FGS,
                EnvironmentConstants.ZOCALO_ENV,
                lambda: generate_start_info_from_num_grids(params),
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
    s4_slit_gaps: Slits


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


PARAMETER_VERSION = Version.parse("1.0.0")


def get_internal_param_version() -> SemanticVersion:
    return SemanticVersion.validate_from_str(str(PARAMETER_VERSION))


class ExternalGridScanParams(BaseModel):
    visit: str
    file_name: str
    storage_directory: str
    exposure_time_s: float
    snapshot_directory: Path
    x_start_um: float
    y_start_um: float
    z_start_um: float
    x_steps: int
    y_steps: int
    beam_size_x: float
    beam_size_y: float
    microns_per_pixel_x: float
    microns_per_pixel_y: float
    upper_left_x: int
    upper_left_y: int
    detector_distance_mm: float
    sample_id: int

    # GDA branch needs to update for these params
    x_step_size_um: PositiveFloat
    y_step_sizes_um: list[PositiveFloat]
    omega_start_deg: int


def get_internal_params(params: ExternalGridScanParams) -> I02_1FgsParams:
    return I02_1FgsParams(
        y_starts_um=[params.y_start_um],
        x_start_um=params.x_start_um,
        z_starts_um=[params.z_start_um],
        omega_starts_deg=[params.omega_start_deg],
        sample_id=params.sample_id,
        visit=params.visit,
        parameter_model_version=get_param_version(),
        file_name=params.file_name,
        storage_directory=params.storage_directory,
        x_steps=params.x_steps,
        y_steps=[params.y_steps],
        path_to_xtal_snapshot=params.snapshot_directory,
        beam_size_x=params.beam_size_x,
        beam_size_y=params.beam_size_y,
        microns_per_pixel_x=params.microns_per_pixel_x,
        microns_per_pixel_y=params.microns_per_pixel_y,
        upper_left_x=params.upper_left_x,
        upper_left_y=params.upper_left_y,
        detector_distance_mm=params.detector_distance_mm,
        ispyb_experiment_type=IspybExperimentType.SAD,
        x_step_size_um=params.x_step_size_um,
        y_step_sizes_um=params.y_step_sizes_um,
    )


def i02_1_gridscan_plan(
    parameters: ExternalGridScanParams,
    composite: FlyScanXRayCentreComposite = inject(""),
) -> MsgGenerator:
    """BlueAPI entry point for i02-1 grid scans"""

    params = get_internal_params(parameters)

    beamline_specific = construct_i02_1_specific_features(composite, params)
    callbacks = create_gridscan_callbacks(params)

    @bpp.subs_decorator(callbacks)
    @ispyb_activation_decorator(params)
    def decorated_flyscan_plan():
        yield from common_flyscan_xray_centre(composite, params, beamline_specific)

    yield from decorated_flyscan_plan()
