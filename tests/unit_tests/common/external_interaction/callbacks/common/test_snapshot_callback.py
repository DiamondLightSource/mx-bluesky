import shutil
from pathlib import Path
from unittest.mock import Mock

import bluesky.plan_stubs as bps
import pytest
from bluesky.preprocessors import run_decorator, set_run_key_decorator
from bluesky.run_engine import RunEngine
from dodal.devices.oav.oav_detector import OAV
from PIL import Image

from mx_bluesky.common.parameters.constants import DocDescriptorNames
from mx_bluesky.hyperion.external_interaction.callbacks.snapshot_callback import (
    BeamDrawingCallback,
)
from mx_bluesky.hyperion.parameters.constants import CONST
from mx_bluesky.hyperion.parameters.rotation import RotationScan

from ......conftest import raw_params_from_file


@pytest.fixture
def params():
    return RotationScan(
        **raw_params_from_file(
            "tests/test_data/parameter_json_files/good_test_rotation_scan_parameters.json"
        )
    )


def simplified_experiment_plan(
    oav: OAV, snapshot_directory: Path, params: RotationScan
):
    @set_run_key_decorator(CONST.PLAN.LOAD_CENTRE_COLLECT)
    @run_decorator(
        md={
            "activate_callbacks": ["BeamDrawingCallback"],
            "with_snapshot": params.model_dump_json(),
        }
    )
    def inner():
        # pretend as if we triggered the oav snapshot
        yield from bps.abs_set(
            oav.snapshot.last_saved_path, str(snapshot_directory / "test_filename.png")
        )
        yield from bps.create(DocDescriptorNames.OAV_ROTATION_SNAPSHOT_TRIGGERED)
        yield from bps.read(oav)
        yield from bps.save()

    yield from inner()


def test_snapshot_callback_loads_and_saves_updated_snapshot_propagates_event(
    tmp_path: Path, RE: RunEngine, oav: OAV, params: RotationScan
):
    downstream_cb = Mock()
    callback = BeamDrawingCallback(emit=downstream_cb)
    base_image_path = tmp_path / "test_filename.png"
    shutil.copy(
        "tests/test_data/test_images/generate_snapshot_input.png", base_image_path
    )

    RE.subscribe(callback)
    RE(simplified_experiment_plan(oav, tmp_path, params))

    expected_image = Image.open(
        "tests/test_data/test_images/generate_snapshot_output.png"
    )
    expected_bytes = expected_image.tobytes()
    generated_image_path = str(tmp_path / "test_filename_with_beam_centre.png")
    generated_image = Image.open(generated_image_path)
    generated_bytes = generated_image.tobytes()
    assert generated_bytes == expected_bytes, "Actual and expected images differ"

    downstream_calls = downstream_cb.mock_calls
    assert downstream_calls[0].args[0] == "start"
    assert downstream_calls[1].args[0] == "descriptor"
    assert downstream_calls[2].args[0] == "event"
    assert (
        downstream_calls[2].args[1]["data"]["oav-snapshot-last_saved_path"]
        == generated_image_path
    )
    assert downstream_calls[3].args[0] == "stop"
