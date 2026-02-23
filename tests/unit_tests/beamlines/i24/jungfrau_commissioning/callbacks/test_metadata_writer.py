from __future__ import annotations

import json
from pathlib import Path

import bluesky.plan_stubs as bps
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
from mx_bluesky.common.experiment_plans.inner_plans.read_hardware import (
    read_hardware_plan,
)
from mx_bluesky.common.external_interaction.callbacks.rotation.ispyb_callback import (
    RotationISPyBCallback,
)
from mx_bluesky.common.parameters.constants import PlanNameConstants
from mx_bluesky.common.parameters.rotation import SingleRotationScan
from tests.expeye_helpers import TEST_DATA_COLLECTION_IDS
from tests.unit_tests.beamlines.i24.jungfrau_commissioning.utils import (
    get_good_single_rotation_params,
)


async def test_metadata_writer_produces_correct_output(
    run_engine: RunEngine,
    tmp_path,
    rotation_composite: RotationScanComposite,
    with_numtracker,
    mock_ispyb_conn,
):
    params = get_good_single_rotation_params(tmp_path)
    metadata_writer = JsonMetadataWriter()

    wavelength = 1
    energy = 1
    det_z = 3

    await rotation_composite.dcm.wavelength_in_a.set(wavelength)
    await rotation_composite.dcm.energy_in_keV.set(energy)
    await rotation_composite.det_stage.z.set(det_z)
    await rotation_composite.jungfrau._writer.file_path.set(tmp_path)

    expected_output = {
        "wavelength_in_a": wavelength,
        "energy_kev": energy,
        "detector_distance_mm": det_z,
        "angular_increment_deg": 0.1,
        "dcid": TEST_DATA_COLLECTION_IDS[0],
    }
    run_engine(
        _do_metadata_writing_read_with_ispyb_callbacks(
            [
                rotation_composite.dcm.energy_in_keV,
                rotation_composite.dcm.wavelength_in_a,
                rotation_composite.det_stage.z,
                rotation_composite.jungfrau._writer.file_path,
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


async def test_assertion_error_if_no_jf_path_found(
    run_engine: RunEngine,
    tmp_path,
    rotation_composite: RotationScanComposite,
    with_numtracker,
    mock_ispyb_conn,
):
    params = get_good_single_rotation_params(tmp_path)
    metadata_writer = JsonMetadataWriter()
    wavelength = 1
    energy = 1
    det_z = 3

    await rotation_composite.dcm.wavelength_in_a.set(wavelength)
    await rotation_composite.dcm.energy_in_keV.set(energy)
    await rotation_composite.det_stage.z.set(det_z)

    with pytest.raises(AssertionError, match="No detector writer path was found"):
        run_engine(
            _do_metadata_writing_read_with_ispyb_callbacks(
                [
                    rotation_composite.dcm.energy_in_keV,
                    rotation_composite.dcm.wavelength_in_a,
                    rotation_composite.det_stage.z,
                    rotation_composite.jungfrau._writer.file_path,
                ],
                params,
                metadata_writer,
            )
        )


def _do_metadata_writing_read_with_ispyb_callbacks(
    signals: list[SignalR | Motor],
    params: SingleRotationScan,
    writer: JsonMetadataWriter,
):
    ispyb_callback = RotationISPyBCallback()

    @bpp.subs_decorator([writer, ispyb_callback])
    @bpp.set_run_key_decorator(PlanNameConstants.ROTATION_OUTER)
    @bpp.run_decorator(
        md={
            "subplan_name": PlanNameConstants.ROTATION_OUTER,
            "mx_bluesky_parameters": params.model_dump_json(),
            "activate_callbacks": ["RotationISPyBCallback"],
        }
    )
    def _rotation_outer():
        yield from bps.null()

        @bpp.set_run_key_decorator(PlanNameConstants.ROTATION_MAIN)
        @bpp.run_decorator(
            md={
                "subplan_name": PlanNameConstants.ROTATION_MAIN,
                "rotation_scan_params": params.model_dump_json(),
                "dcid": ispyb_callback.ispyb_ids,
            }
        )
        def _rotation_main():
            yield from read_hardware_plan(
                signals,
                PlanNameConstants.ROTATION_DEVICE_READ,
            )

        yield from _rotation_main()

    yield from _rotation_outer()
