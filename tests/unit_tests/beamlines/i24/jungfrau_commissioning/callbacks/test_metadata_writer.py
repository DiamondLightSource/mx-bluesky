from __future__ import annotations

import json
from pathlib import Path

import bluesky.preprocessors as bpp
import pytest
from bluesky.run_engine import RunEngine
from numpy.testing import assert_allclose
from ophyd_async.core import SignalR
from ophyd_async.epics.motor import Motor

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
from mx_bluesky.common.parameters.rotation import SingleRotationScan
from tests.unit_tests.beamlines.i24.jungfrau_commissioning.utils import (
    get_good_single_rotation_params,
)


async def test_metadata_writer_produces_correct_output(
    run_engine: RunEngine, tmp_path, rotation_composite: RotationScanComposite
):
    params = get_good_single_rotation_params(tmp_path)
    metadata_writer = JsonMetadataWriter()

    wavelength = 1
    energy = 1
    det_z = 3

    await rotation_composite.dcm.wavelength_in_a.set(wavelength)
    await rotation_composite.dcm.energy_in_keV.set(energy)
    await rotation_composite.detector_motion.z.set(det_z)
    await rotation_composite.jungfrau.writer.file_path.set(tmp_path)

    expected_output = {
        "wavelength_in_a": wavelength,
        "energy_kev": energy,
        "detector_distance_mm": det_z,
        "angular_increment_deg": 0.1,
    }
    run_engine(
        _do_metadata_writing_read(
            [
                rotation_composite.dcm.energy_in_keV,
                rotation_composite.dcm.wavelength_in_a,
                rotation_composite.detector_motion.z,
                rotation_composite.jungfrau.writer.file_path,
            ],
            params,
            metadata_writer,
        )
    )

    assert metadata_writer.final_path == tmp_path

    with open(Path(tmp_path) / READING_DUMP_FILENAME) as f:
        actual_output = json.load(f)
    assert expected_output.keys() == actual_output.keys()
    for key in actual_output:
        assert_allclose(actual_output[key], expected_output[key])


async def test_metadata_writer_writes_into_a_collection_directory_it_cannot_see(
    run_engine: RunEngine, tmp_path, rotation_composite: RotationScanComposite
):
    """The detector IOC creates the collection directory from another NFS client, after
    we have looked the path up to prepare the writer, so this client can be holding a
    cached negative lookup for a directory that does exist. The nearest we can get to
    that here is a directory which is genuinely absent."""
    params = get_good_single_rotation_params(tmp_path)
    metadata_writer = JsonMetadataWriter()
    collection_directory = tmp_path / "0007_jungfrau"

    await rotation_composite.dcm.wavelength_in_a.set(1)
    await rotation_composite.dcm.energy_in_keV.set(1)
    await rotation_composite.detector_motion.z.set(3)
    await rotation_composite.jungfrau.writer.file_path.set(collection_directory)

    run_engine(
        _do_metadata_writing_read(
            [
                rotation_composite.dcm.energy_in_keV,
                rotation_composite.dcm.wavelength_in_a,
                rotation_composite.detector_motion.z,
                rotation_composite.jungfrau.writer.file_path,
            ],
            params,
            metadata_writer,
        )
    )

    assert (collection_directory / READING_DUMP_FILENAME).exists()


async def test_assertion_error_if_no_jf_path_found(
    run_engine: RunEngine, tmp_path, rotation_composite: RotationScanComposite
):
    params = get_good_single_rotation_params(tmp_path)
    metadata_writer = JsonMetadataWriter()
    wavelength = 1
    energy = 1
    det_z = 3

    await rotation_composite.dcm.wavelength_in_a.set(wavelength)
    await rotation_composite.dcm.energy_in_keV.set(energy)
    await rotation_composite.detector_motion.z.set(det_z)

    with pytest.raises(AssertionError, match="No detector writer path was found"):
        run_engine(
            _do_metadata_writing_read(
                [
                    rotation_composite.dcm.energy_in_keV,
                    rotation_composite.dcm.wavelength_in_a,
                    rotation_composite.detector_motion.z,
                    rotation_composite.jungfrau.writer.file_path,
                ],
                params,
                metadata_writer,
            )
        )


def _do_metadata_writing_read(
    signals: list[SignalR | Motor],
    params: SingleRotationScan,
    writer: JsonMetadataWriter,
):
    @bpp.subs_decorator([writer])
    @bpp.set_run_key_decorator(PlanNameConstants.ROTATION_MAIN)
    @bpp.run_decorator(
        md={
            "subplan_name": PlanNameConstants.ROTATION_MAIN,
            "rotation_scan_params": params.model_dump_json(),
        }
    )
    def _inner_read():
        yield from read_hardware_plan(
            signals,
            PlanNameConstants.ROTATION_DEVICE_READ,
        )

    yield from _inner_read()
