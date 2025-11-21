import bluesky.preprocessors as bpp
from bluesky.utils import MsgGenerator
from dodal.common import inject
from dodal.devices.attenuator.attenuator import EnumFilterAttenuator
from dodal.devices.hutch_shutter import HutchShutter
from dodal.devices.i24.aperture import Aperture
from dodal.devices.i24.beamstop import Beamstop
from dodal.devices.i24.commissioning_jungfrau import CommissioningJungfrau
from dodal.devices.i24.dcm import DCM
from dodal.devices.i24.dual_backlight import DualBacklight
from dodal.devices.i24.vgonio import VerticalGoniometer
from dodal.devices.motors import YZStage
from dodal.devices.synchrotron import Synchrotron
from dodal.devices.xbpm_feedback import XBPMFeedback
from dodal.devices.zebra.zebra import Zebra
from dodal.devices.zebra.zebra_controlled_shutter import ZebraShutter

from mx_bluesky.beamlines.i24.jungfrau_commissioning.composites import (
    RotationScanComposite,
)
from mx_bluesky.beamlines.i24.jungfrau_commissioning.experiment_plans.rotation_scan_plan import (
    multi_rotation_plan_varying_transmission,
    single_rotation_plan,
)
from mx_bluesky.beamlines.i24.parameters.rotation import (
    MultiRotationScanByTransmissions,
)
from mx_bluesky.common.parameters.rotation import SingleRotationScan

PARAM_MODEL_VERSION = "5.0.0"
BEAMLINE = "BL24I"


@bpp.run_decorator()
def run_single_rotation_plan(
    exposure_time_s: float,
    omega_start_deg: float,
    omega_increment_deg: float,
    total_scan_width_deg: float,
    detector_distance_mm: float,
    shutter_opening_time_s: float,
    visit: str,
    file_name: str,
    storage_directory: str,
    transmission: float,
    aperture: Aperture = inject("aperture"),
    attenuator: EnumFilterAttenuator = inject("attenuator"),
    jungfrau: CommissioningJungfrau = inject("commissioning_jungfrau"),
    gonio: VerticalGoniometer = inject("vgonio"),
    synchrotron: Synchrotron = inject("synchrotron"),
    sample_shutter: ZebraShutter = inject("sample_shutter"),
    zebra: Zebra = inject("zebra"),
    xbpm_feedback: XBPMFeedback = inject("xbpm_feedback"),
    hutch_shutter: HutchShutter = inject("shutter"),
    beamstop: Beamstop = inject("beamstop"),
    detector_stage: YZStage = inject("detector_motion"),
    backlight: DualBacklight = inject("backlight"),
    dcm: DCM = inject("dcm"),
) -> MsgGenerator:
    composite = RotationScanComposite(
        aperture,
        attenuator,
        jungfrau,
        gonio,
        synchrotron,
        sample_shutter,
        zebra,
        xbpm_feedback,
        hutch_shutter,
        beamstop,
        detector_stage,
        backlight,
        dcm,
    )
    parameters = SingleRotationScan(
        exposure_time_s=exposure_time_s,
        omega_start_deg=omega_start_deg,
        rotation_increment_deg=omega_increment_deg,
        scan_width_deg=total_scan_width_deg,
        detector_distance_mm=detector_distance_mm,
        visit=visit,
        file_name=file_name,
        storage_directory=storage_directory,
        shutter_opening_time_s=shutter_opening_time_s,
        transmission_frac=transmission,
        parameter_model_version=PARAM_MODEL_VERSION,
        beamline="BL24I",
        sample_id=0,
        snapshot_directory=None,
    )

    yield from single_rotation_plan(composite, parameters)


@bpp.run_decorator()
def run_multi_rotation_plan(
    exposure_time_s: float,
    omega_start_deg: float,
    omega_increment_deg: float,
    total_scan_width_deg: float,
    detector_distance_mm: float,
    shutter_opening_time_s: float,
    visit: str,
    file_name: str,
    storage_directory: str,
    transmission_fractions: list[float],
    aperture: Aperture = inject("aperture"),
    attenuator: EnumFilterAttenuator = inject("attenuator"),
    jungfrau: CommissioningJungfrau = inject("commissioning_jungfrau"),
    gonio: VerticalGoniometer = inject("vgonio"),
    synchrotron: Synchrotron = inject("synchrotron"),
    sample_shutter: ZebraShutter = inject("sample_shutter"),
    zebra: Zebra = inject("zebra"),
    xbpm_feedback: XBPMFeedback = inject("xbpm_feedback"),
    hutch_shutter: HutchShutter = inject("shutter"),
    beamstop: Beamstop = inject("beamstop"),
    detector_stage: YZStage = inject("detector_motion"),
    backlight: DualBacklight = inject("backlight"),
    dcm: DCM = inject("dcm"),
) -> MsgGenerator:
    composite = RotationScanComposite(
        aperture,
        attenuator,
        jungfrau,
        gonio,
        synchrotron,
        sample_shutter,
        zebra,
        xbpm_feedback,
        hutch_shutter,
        beamstop,
        detector_stage,
        backlight,
        dcm,
    )
    params = MultiRotationScanByTransmissions(
        exposure_time_s=exposure_time_s,
        omega_start_deg=omega_start_deg,
        rotation_increment_deg=omega_increment_deg,
        scan_width_deg=total_scan_width_deg,
        detector_distance_mm=detector_distance_mm,
        visit=visit,
        file_name=file_name,
        storage_directory=storage_directory,
        shutter_opening_time_s=shutter_opening_time_s,
        transmission_frac=-1,
        transmission_fractions=transmission_fractions,
        parameter_model_version=PARAM_MODEL_VERSION,
        beamline="BL24I",
        sample_id=0,
        snapshot_directory=None,
    )
    yield from multi_rotation_plan_varying_transmission(composite, params)
