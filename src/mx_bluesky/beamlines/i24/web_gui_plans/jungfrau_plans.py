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
    exp_time: float,
    omega_start: float,
    omega_increment: float,
    det_distance: float,
    sample_id: int,
    transmissions: list[float],
    composite: RotationScanComposite = inject(),
):
    params = ExternalRotationScanParams(
        transmission_fractions=transmissions,
        exposure_time_s=exp_time,
        omega_start_deg=omega_start,
        rotation_increment_per_image_deg=omega_increment,
        filename=filename,
        detector_distance_mm=det_distance,
        sample_id=sample_id,
    )

    yield from rotation_scan_plan(composite, params)
