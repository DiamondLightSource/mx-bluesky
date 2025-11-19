import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
from bluesky.utils import MsgGenerator

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
) -> MsgGenerator:
    # params = SingleRotationScan(
    #     exposure_time_s=exposure_time_s,
    #     omega_start_deg=omega_start_deg,
    #     rotation_increment_deg=omega_increment_deg,
    #     scan_width_deg=total_scan_width_deg,
    #     detector_distance_mm=detector_distance_mm,
    #     visit=visit,
    #     file_name=file_name,
    #     storage_directory=storage_directory,
    #     shutter_opening_time_s=shutter_opening_time_s,
    #     transmission_frac=transmission,
    #     parameter_model_version=PARAM_MODEL_VERSION,
    #     beamline="BL24I",
    #     sample_id=0,
    # )

    yield from bps.null()


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
) -> MsgGenerator:
    yield from bps.null()
