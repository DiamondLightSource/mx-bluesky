from __future__ import annotations

from functools import partial

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
from bluesky.utils import MsgGenerator
from dodal.common import inject
from dodal.devices.aperturescatterguard import ApertureScatterguard, ApertureValue
from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
from dodal.devices.backlight import Backlight
from dodal.devices.common_dcm import DoubleCrystalMonochromator
from dodal.devices.detector.detector_motion import DetectorMotion
from dodal.devices.eiger import EigerDetector
from dodal.devices.fast_grid_scan import (
    ZebraFastGridScanThreeD,
    set_fast_grid_scan_params,
)
from dodal.devices.flux import Flux
from dodal.devices.i04.transfocator import Transfocator
from dodal.devices.mx_phase1.beamstop import Beamstop
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.oav.pin_image_recognition import PinTipDetection
from dodal.devices.robot import BartRobot
from dodal.devices.s4_slit_gaps import S4SlitGaps
from dodal.devices.smargon import Smargon
from dodal.devices.synchrotron import Synchrotron
from dodal.devices.undulator import Undulator
from dodal.devices.xbpm_feedback import XBPMFeedback
from dodal.devices.zebra.zebra import Zebra
from dodal.devices.zebra.zebra_controlled_shutter import ZebraShutter
from dodal.devices.zocalo import ZocaloResults
from dodal.plans.preprocessors.verify_undulator_gap import (
    verify_undulator_gap_before_run_decorator,
)

from mx_bluesky.beamlines.i04.external_interaction.config_server import (
    get_i04_config_client,
)
from mx_bluesky.common.device_setup_plans.setup_zebra_and_shutter import (
    setup_zebra_for_gridscan,
    tidy_up_zebra_after_gridscan,
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
    generate_start_info_from_omega_map,
)
from mx_bluesky.common.external_interaction.callbacks.xray_centre.nexus_callback import (
    GridscanNexusFileCallback,
)
from mx_bluesky.common.parameters.constants import (
    EnvironmentConstants,
    OavConstants,
    PlanGroupCheckpointConstants,
    PlanNameConstants,
)
from mx_bluesky.common.parameters.device_composites import (
    GridDetectThenXRayCentreComposite,
)
from mx_bluesky.common.parameters.gridscan import GridCommon, SpecifiedThreeDGridScan
from mx_bluesky.common.preprocessors.preprocessors import (
    transmission_and_xbpm_feedback_for_collection_decorator,
)
from mx_bluesky.common.utils.log import LOGGER

DEFAULT_BEAMSIZE_MICRONS = 20


def _change_beamsize(
    transfocator: Transfocator, beamsize: float, parameters: GridCommon
):
    """i04 always uses the large aperture and changes beamsize with the transfocator.

    An aperture is needed to reduce scatter but the transfocator is best used for beamsize
    changes as it gives more flux compared to a bigger beam with a small aperture.
    """
    parameters.selected_aperture = ApertureValue.LARGE
    yield from bps.abs_set(
        transfocator, beamsize, group=PlanGroupCheckpointConstants.GRID_READY_FOR_DC
    )


# See https://github.com/DiamondLightSource/blueapi/issues/506 for using device composites
def i04_grid_detect_then_xray_centre(
    parameters: GridCommon,
    aperture_scatterguard: ApertureScatterguard = inject("aperture_scatterguard"),
    attenuator: BinaryFilterAttenuator = inject("attenuator"),
    backlight: Backlight = inject("backlight"),
    beamstop: Beamstop = inject("beamstop"),
    dcm: DoubleCrystalMonochromator = inject("dcm"),
    zebra_fast_grid_scan: ZebraFastGridScanThreeD = inject("zebra_fast_grid_scan"),
    flux: Flux = inject("flux"),
    oav: OAV = inject("oav"),
    pin_tip_detection: PinTipDetection = inject("pin_tip_detection"),
    s4_slit_gaps: S4SlitGaps = inject("s4_slit_gaps"),
    undulator: Undulator = inject("undulator"),
    xbpm_feedback: XBPMFeedback = inject("xbpm_feedback"),
    zebra: Zebra = inject("zebra"),
    robot: BartRobot = inject("robot"),
    sample_shutter: ZebraShutter = inject("sample_shutter"),
    eiger: EigerDetector = inject("eiger"),
    synchrotron: Synchrotron = inject("synchrotron"),
    zocalo: ZocaloResults = inject("zocalo"),
    smargon: Smargon = inject("smargon"),
    detector_motion: DetectorMotion = inject("detector_motion"),
    transfocator: Transfocator = inject("transfocator"),
    oav_config: str = OavConstants.OAV_CONFIG_JSON,
    udc: bool = False,
) -> MsgGenerator:
    """
    A composite plan which:
    - Uses the OAV to draw a virtual grid over the sample and to take snapshots of the sample
    - Scans through the grid to identify the crystal centre
    - Changes the aperture to match the beam size to the crystal size
    - Moves the sample to the crystal centre of mass


    i04's implementation of this plan is very similar to Hyperion. However, since i04
    isn't running in a continuous Bluesky UDC loop, we take additional steps in beamline
    tidy-up.
    """

    composite = GridDetectThenXRayCentreComposite(
        eiger,
        synchrotron,
        zocalo,
        smargon,
        aperture_scatterguard,
        attenuator,
        backlight,
        beamstop,
        dcm,
        detector_motion,
        zebra_fast_grid_scan,
        flux,
        oav,
        pin_tip_detection,
        s4_slit_gaps,
        undulator,
        xbpm_feedback,
        zebra,
        robot,
        sample_shutter,
    )
    initial_beamsize = yield from bps.rd(transfocator.beamsize_set_microns)

    current_wavelength_a = yield from bps.rd(composite.dcm.wavelength_in_a)

    parameters.transmission_frac, parameters.exposure_time_s = (
        _fix_transmission_and_exposure_time_for_current_wavelength(
            parameters.transmission_frac,
            parameters.exposure_time_s,
            current_wavelength_a,
        )
    )

    def tidy_beamline():
        if not udc:
            yield from get_ready_for_oav_and_close_shutter(
                composite.smargon,
                composite.backlight,
                composite.aperture_scatterguard,
                composite.detector_motion,
            )
        yield from bps.mv(transfocator, initial_beamsize)

    @bpp.finalize_decorator(tidy_beamline)
    def _inner_grid_detect_then_xrc():
        # These callbacks let us talk to ISPyB and Nexgen. They aren't included in the common plan because
        # Hyperion handles its callbacks differently to BlueAPI-managed plans, see
        # https://github.com/DiamondLightSource/mx-bluesky/issues/1117
        callbacks = create_gridscan_callbacks()

        @bpp.subs_decorator(callbacks)
        @verify_undulator_gap_before_run_decorator(composite)
        @transmission_and_xbpm_feedback_for_collection_decorator(
            composite, parameters.transmission_frac, PlanNameConstants.GRIDSCAN_OUTER
        )
        def grid_detect_then_xray_centre_with_callbacks():
            yield from grid_detect_then_xray_centre(
                composite=composite,
                parameters=parameters,
                xrc_params_type=SpecifiedThreeDGridScan,
                construct_beamline_specific=construct_i04_specific_features,
                oav_config=oav_config,
            )

        yield from grid_detect_then_xray_centre_with_callbacks()

    yield from _change_beamsize(transfocator, DEFAULT_BEAMSIZE_MICRONS, parameters)
    yield from _inner_grid_detect_then_xrc()


def _fix_transmission_and_exposure_time_for_current_wavelength(
    original_trans_frac: float,
    original_exposure_time_s: float,
    current_wavelength_a: float,
):
    """
    The transmission and exposure time sent when GDA triggers their plan through the
    client's "auto XRC button" assumes that the energy is at a certain value.
    This reads the current energy, compares it to the assumed energy, and adjusts transmission and exposure time
    accordingly to ensure there's enough signal on the detector.
    """

    assumed_wavelength_a = (
        get_i04_config_client().get_feature_flags().ASSUMED_WAVELENGTH_IN_A
    )
    wavelength_scale = (assumed_wavelength_a / current_wavelength_a) ** 2

    # Transmission frac needed to get ideal signal
    ideal_trans_frac = original_trans_frac * wavelength_scale
    if ideal_trans_frac <= 1:
        new_trans_frac = ideal_trans_frac
        new_exposure_time_s = original_exposure_time_s
    else:
        # If the scaling would result in transmission fraction > 1,
        # cap it to 1, find remaining scaling needed, and apply it
        # to exposure time instead.
        new_trans_frac = 1
        scaling_applied_to_trans = new_trans_frac / ideal_trans_frac
        remaining_scaling_needed = wavelength_scale / scaling_applied_to_trans
        new_exposure_time_s = original_exposure_time_s * remaining_scaling_needed

    LOGGER.info(
        f"Fixing transmission fraction to {new_trans_frac} and exposure time to {new_exposure_time_s}s"
    )

    # Exposure time in FGS IOC is in ms, and must be an integer, so round it here
    return new_trans_frac, round(new_exposure_time_s, 3)


def get_ready_for_oav_and_close_shutter(
    smargon: Smargon,
    backlight: Backlight,
    aperture_scatterguard: ApertureScatterguard,
    detector_motion: DetectorMotion,
):
    yield from bps.wait(PlanGroupCheckpointConstants.GRID_READY_FOR_DC)
    group = "get_ready_for_oav_and_close_shutter"
    LOGGER.info("Non-udc tidy: Setting up beamline for OAV")
    yield from setup_beamline_for_OAV(
        smargon, backlight, aperture_scatterguard, group=group
    )
    LOGGER.info("Non-udc tidy: Closing detector shutter")
    yield from bps.abs_set(
        detector_motion.shutter,
        0,
        group=group,
    )
    yield from bps.wait(group)


def create_gridscan_callbacks() -> tuple[
    GridscanNexusFileCallback, GridscanISPyBCallback
]:
    return (
        GridscanNexusFileCallback(param_type=SpecifiedThreeDGridScan),
        GridscanISPyBCallback(
            param_type=GridCommon,
            emit=ZocaloCallback(
                PlanNameConstants.DO_FGS,
                EnvironmentConstants.ZOCALO_ENV,
                generate_start_info_from_omega_map,
            ),
        ),
    )


def construct_i04_specific_features(
    xrc_composite: GridDetectThenXRayCentreComposite,
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

    tidy_plan = partial(
        tidy_up_zebra_after_gridscan,
        xrc_composite.zebra,
        xrc_composite.sample_shutter,
        group="flyscan_zebra_tidy",
        wait=True,
    )
    set_flyscan_params_plan = partial(
        set_fast_grid_scan_params,
        xrc_composite.zebra_fast_grid_scan,
        xrc_parameters.FGS_params,
    )
    fgs_motors = xrc_composite.zebra_fast_grid_scan
    return construct_beamline_specific_FGS_features(
        partial(
            setup_zebra_for_gridscan,
        ),
        tidy_plan,
        set_flyscan_params_plan,
        fgs_motors,
        signals_to_read_pre_flyscan,
        signals_to_read_during_collection,
        get_xrc_results_from_zocalo=True,
    )
