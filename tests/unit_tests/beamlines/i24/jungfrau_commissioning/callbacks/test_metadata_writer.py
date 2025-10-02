from __future__ import annotations

import json
from pathlib import Path

import bluesky.preprocessors as bpp
from bluesky.run_engine import RunEngine
from numpy.testing import assert_allclose

from mx_bluesky.beamlines.i24.jungfrau_commissioning.callbacks.metadata_writer import (
    JsonMetadataWriter,
)
from mx_bluesky.beamlines.i24.jungfrau_commissioning.rotation_scan_plan import (
    READING_DUMP_FILENAME,
    RotationScanComposite,
)
from mx_bluesky.beamlines.i24.jungfrau_commissioning.utility_plans import (
    read_devices_for_metadata,
)
from mx_bluesky.beamlines.i24.parameters.constants import (
    PlanNameConstants as I24PlanNameConstants,
)
from tests.unit_tests.beamlines.i24.jungfrau_commissioning.utils import (
    get_good_single_rotation_params,
)


async def test_metadata_writer_produces_correct_output(
    RE: RunEngine, tmp_path, rotation_composite: RotationScanComposite
):
    params = get_good_single_rotation_params(tmp_path)
    metadata_writer = JsonMetadataWriter()

    @bpp.subs_decorator([metadata_writer])
    @bpp.set_run_key_decorator(I24PlanNameConstants.ROTATION_META_READ)
    @bpp.run_decorator(
        md={
            "subplan_name": I24PlanNameConstants.ROTATION_META_READ,
            "scan_points": [params.scan_points],
            "rotation_scan_params": params.model_dump_json(),
        }
    )
    # Write metadata json file
    def _do_read():
        yield from read_devices_for_metadata(rotation_composite)

    wavelength = 1
    energy = 1
    det_z = 3

    await rotation_composite.dcm.wavelength_in_a.set(wavelength)
    await rotation_composite.dcm.energy_in_kev.set(energy)
    await rotation_composite.det_stage.z.set(det_z)
    beam_center = params.detector_params.get_beam_position_mm(det_z)

    expected_output = {
        "wavelength_in_a": wavelength,
        "energy_kev": energy,
        "detector_distance_mm": det_z,
        "angular_increment_deg": 0.1,
        "beam_xy_mm": beam_center,
    }
    RE(_do_read())

    with open(Path(params.storage_directory) / READING_DUMP_FILENAME) as f:
        actual_output = json.load(f)
    assert expected_output.keys() == actual_output.keys()
    for key in actual_output:
        assert_allclose(actual_output[key], expected_output[key])
