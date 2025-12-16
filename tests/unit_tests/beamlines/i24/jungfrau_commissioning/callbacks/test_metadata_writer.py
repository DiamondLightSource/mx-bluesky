from __future__ import annotations

import json
from pathlib import Path

import bluesky.preprocessors as bpp
from bluesky.run_engine import RunEngine
from numpy.testing import assert_allclose

from mx_bluesky.beamlines.i24.jungfrau_commissioning.callbacks.metadata_writer import (
    READING_DUMP_FILENAME,
    JsonMetadataWriter,
)
from mx_bluesky.beamlines.i24.jungfrau_commissioning.experiment_plans.rotation_scan_plan import (
    RotationScanComposite,
)
from mx_bluesky.beamlines.i24.parameters.constants import PlanNameConstants
from mx_bluesky.common.experiment_plans.inner_plans.read_hardware import (
    read_hardware_plan,
)
from tests.unit_tests.beamlines.i24.jungfrau_commissioning.utils import (
    get_good_single_rotation_params,
)


async def test_metadata_writer_produces_correct_output(
    run_engine: RunEngine, tmp_path, rotation_composite: RotationScanComposite
):
    params = get_good_single_rotation_params(tmp_path)
    metadata_writer = JsonMetadataWriter()

    @bpp.subs_decorator([metadata_writer])
    @bpp.set_run_key_decorator(PlanNameConstants.ROTATION_MAIN)
    @bpp.run_decorator(
        md={
            "subplan_name": PlanNameConstants.ROTATION_MAIN,
            "scan_points": [params.scan_points],
            "rotation_scan_params": params.model_dump_json(),
        }
    )
    def _do_read():
        yield from read_hardware_plan(
            [
                rotation_composite.dcm.energy_in_keV,
                rotation_composite.dcm.wavelength_in_a,
                rotation_composite.det_stage.z,
            ],
            PlanNameConstants.ROTATION_DEVICE_READ,
        )

    wavelength = 1
    energy = 1
    det_z = 3

    await rotation_composite.dcm.wavelength_in_a.set(wavelength)
    await rotation_composite.dcm.energy_in_keV.set(energy)
    await rotation_composite.det_stage.z.set(det_z)

    expected_output = {
        "wavelength_in_a": wavelength,
        "energy_kev": energy,
        "detector_distance_mm": det_z,
        "angular_increment_deg": 0.1,
    }
    run_engine(_do_read())

    with open(Path(params.storage_directory) / READING_DUMP_FILENAME) as f:
        actual_output = json.load(f)
    assert expected_output.keys() == actual_output.keys()
    for key in actual_output:
        assert_allclose(actual_output[key], expected_output[key])
