import bluesky.preprocessors as bpp
from dodal.common import inject

from mx_bluesky.beamlines.i24.jungfrau_commissioning.composites import (
    RotationScanComposite,
)
from mx_bluesky.beamlines.i24.jungfrau_commissioning.experiment_plans.rotation_scan_plan import (
    ExternalRotationScanParams,
    rotation_scan_plan,
)


@bpp.run_decorator()
def gui_run_jf_rotation_scan(
    filename: str,
    exposure_time_s: float,
    omega_start_deg: float,
    omega_increment_deg: float,
    det_distance_mm: float,
    sample_id: int,
    transmissions: list[float],
    composite: RotationScanComposite = inject(),
):
    params = ExternalRotationScanParams(
        transmission_fractions=transmissions,
        exposure_time_s=exposure_time_s,
        omega_start_deg=omega_start_deg,
        rotation_increment_per_image_deg=omega_increment_deg,
        filename=filename,
        detector_distance_mm=det_distance_mm,
        sample_id=sample_id,
    )

    yield from rotation_scan_plan(composite, params)
