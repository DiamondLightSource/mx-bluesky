import os
from functools import partial
from pathlib import Path
from unittest.mock import MagicMock, Mock

import bluesky.plan_stubs as bps
import pytest
from bluesky.preprocessors import run_decorator, set_run_key_decorator
from bluesky.run_engine import RunEngine
from dodal.devices.areadetector.plugins.MJPG import MJPG
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.smargon import Smargon
from ophyd_async.core import AsyncStatus
from PIL import Image

from mx_bluesky.common.parameters.components import WithSnapshot
from mx_bluesky.common.parameters.constants import DocDescriptorNames
from mx_bluesky.hyperion.external_interaction.callbacks.snapshot_callback import (
    BeamDrawingCallback,
)
from mx_bluesky.hyperion.parameters.constants import CONST
from mx_bluesky.hyperion.parameters.rotation import RotationScan

from ......conftest import assert_images_pixelwise_equal, raw_params_from_file


@pytest.fixture
def params_take_snapshots():
    return RotationScan(
        **raw_params_from_file(
            "tests/test_data/parameter_json_files/good_test_rotation_scan_parameters.json"
        )
    )


@pytest.fixture
def params_generate_from_grid_snapshots(params_take_snapshots):
    params_take_snapshots.use_grid_snapshots = True
    return params_take_snapshots


@pytest.fixture
def oav_with_snapshots(oav: OAV):
    @AsyncStatus.wrap
    async def fake_trigger(mjpg: MJPG):
        with Image.open(
            "tests/test_data/test_images/generate_snapshot_input.png"
        ) as image:
            await mjpg.post_processing(image)

    oav.snapshot.trigger = MagicMock(side_effect=partial(fake_trigger, oav.snapshot))
    oav.grid_snapshot.trigger.side_effect = MagicMock(
        side_effect=partial(fake_trigger, oav.grid_snapshot)
    )
    yield oav


def simple_rotation_snapshot_plan(
    oav: OAV, snapshot_directory: Path, params: WithSnapshot
):
    @set_run_key_decorator(CONST.PLAN.LOAD_CENTRE_COLLECT)
    @run_decorator(
        md={
            "activate_callbacks": ["BeamDrawingCallback"],
            "with_snapshot": params.model_dump_json(),
        }
    )
    def inner():
        yield from bps.abs_set(oav.snapshot.directory, str(snapshot_directory))
        yield from bps.abs_set(oav.snapshot.filename, "test_filename")
        yield from bps.trigger(oav.snapshot, wait=True)
        yield from bps.create(DocDescriptorNames.OAV_ROTATION_SNAPSHOT_TRIGGERED)
        yield from bps.read(oav)
        yield from bps.save()

    yield from inner()


def simple_take_grid_snapshot_and_generate_rotation_snapshot_plan(
    oav: OAV, smargon: Smargon, snapshot_directory: Path, params: WithSnapshot
):
    @set_run_key_decorator(CONST.PLAN.LOAD_CENTRE_COLLECT)
    @run_decorator(
        md={
            "activate_callbacks": ["BeamDrawingCallback"],
            "with_snapshot": WithSnapshot.model_validate(
                {
                    "snapshot_directory": snapshot_directory,
                    "snapshot_omegas_deg": [0, 270],
                    "use_grid_snapshots": True,
                }
            ).model_dump_json(),
        }
    )
    def inner():
        grid_snapshot_dir = snapshot_directory / "grid_snapshots"
        rotation_snapshot_dir = snapshot_directory / "rotation_snapshots"
        os.mkdir(grid_snapshot_dir)
        os.mkdir(rotation_snapshot_dir)
        for omega in (
            0,
            -90,
        ):
            yield from bps.abs_set(smargon.omega, omega, wait=True)
            yield from bps.abs_set(
                oav.grid_snapshot.directory, str(grid_snapshot_dir), wait=True
            )
            yield from bps.abs_set(
                oav.grid_snapshot.filename,
                f"my_grid_snapshot_prefix_{omega}",
                wait=True,
            )
            yield from bps.trigger(oav.grid_snapshot, wait=True)
            yield from bps.create(DocDescriptorNames.OAV_GRID_SNAPSHOT_TRIGGERED)
            yield from bps.read(oav)  # Capture base image path
            yield from bps.read(smargon)  # Capture base image sample x, y, z, omega
            yield from bps.save()
        yield from bps.mvr(smargon.x, 0.4, smargon.y, 0.25, smargon.z, 0.5)
        yield from bps.wait()
        for omega in (
            0,
            270,
        ):
            yield from bps.abs_set(
                oav.snapshot.last_saved_path,
                str(rotation_snapshot_dir / f"my_snapshot_prefix_{omega}.png"),
            )
            yield from bps.create(DocDescriptorNames.OAV_ROTATION_SNAPSHOT_TRIGGERED)
            yield from bps.read(oav)  # Capture path info for generated snapshot
            yield from bps.read(smargon)  # Capture the current sample x, y, z
            yield from bps.save()

    yield from inner()


def test_snapshot_callback_generate_snapshot_from_gridscan(
    tmp_path: Path,
    RE: RunEngine,
    oav_with_snapshots: OAV,
    smargon: Smargon,
    params_generate_from_grid_snapshots: RotationScan,
):
    downstream_cb = Mock()
    callback = BeamDrawingCallback(emit=downstream_cb)

    RE.subscribe(callback)
    RE(
        simple_take_grid_snapshot_and_generate_rotation_snapshot_plan(
            oav_with_snapshots, smargon, tmp_path, params_generate_from_grid_snapshots
        )
    )

    downstream_calls = downstream_cb.mock_calls
    event_names_to_descriptors = {
        c.args[1]["name"]: c.args[1]["uid"]
        for c in downstream_calls
        if c.args[0] == "descriptor"
    }
    rotation_snapshot_events = [
        c.args[1]["data"]
        for c in downstream_calls
        if c.args[0] == "event"
        and c.args[1]["descriptor"]
        == event_names_to_descriptors[
            DocDescriptorNames.OAV_ROTATION_SNAPSHOT_TRIGGERED
        ]
    ]

    for i, omega in {0: 0, 1: 270}.items():
        generated_image_path = str(
            tmp_path / f"rotation_snapshots/my_snapshot_prefix_{omega}.png"
        )
        assert_images_pixelwise_equal(
            generated_image_path,
            "tests/test_data/test_images/generate_snapshot_output.png",
        )
        assert (
            rotation_snapshot_events[i]["oav-snapshot-last_saved_path"]
            == generated_image_path
        )


def test_snapshot_callback_loads_and_saves_updated_snapshot_propagates_event(
    tmp_path: Path,
    RE: RunEngine,
    oav_with_snapshots: OAV,
    params_take_snapshots: RotationScan,
):
    oav = oav_with_snapshots
    downstream_cb = Mock()
    callback = BeamDrawingCallback(emit=downstream_cb)

    RE.subscribe(callback)
    RE(simple_rotation_snapshot_plan(oav, tmp_path, params_take_snapshots))

    generated_image_path = str(tmp_path / "test_filename_with_beam_centre.png")
    assert_images_pixelwise_equal(
        generated_image_path, "tests/test_data/test_images/generate_snapshot_output.png"
    )

    downstream_calls = downstream_cb.mock_calls
    assert downstream_calls[0].args[0] == "start"
    assert downstream_calls[1].args[0] == "descriptor"
    assert downstream_calls[2].args[0] == "event"
    assert (
        downstream_calls[2].args[1]["data"]["oav-snapshot-last_saved_path"]
        == generated_image_path
    )
    assert downstream_calls[3].args[0] == "stop"
