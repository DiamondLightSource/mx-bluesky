import os
from collections.abc import Sequence
from functools import partial
from pathlib import Path
from unittest.mock import ANY, MagicMock, Mock, call, patch

import bluesky.plan_stubs as bps
import pytest
from _pytest.fixtures import FixtureRequest
from bluesky.preprocessors import run_decorator, set_run_key_decorator
from bluesky.run_engine import RunEngine
from dodal.devices.areadetector.plugins.MJPG import MJPG
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.smargon import Smargon
from ophyd_async.core import AsyncStatus
from ophyd_async.testing import set_mock_value
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
def next_snapshot():
    return MagicMock(
        return_value="tests/test_data/test_images/generate_snapshot_input.png"
    )


@pytest.fixture
def oav_with_snapshots(oav: OAV, next_snapshot):
    @AsyncStatus.wrap
    async def fake_trigger(mjpg: MJPG):
        with Image.open(next_snapshot()) as image:
            # don't do full post-processing to save on slow PIL image save calls
            await mjpg._save_image(image)

    oav.snapshot.trigger = MagicMock(side_effect=partial(fake_trigger, oav.snapshot))
    oav.grid_snapshot.trigger = MagicMock(
        side_effect=partial(fake_trigger, oav.grid_snapshot)
    )
    yield oav


@pytest.fixture(autouse=True)
def optimise_pil_for_speed():
    with patch(
        "mx_bluesky.hyperion.external_interaction.callbacks.snapshot_callback.COMPRESSION_LEVEL",
        1,
    ):
        yield


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
    oav: OAV,
    smargon: Smargon,
    snapshot_directory: Path,
    chis: Sequence[int] = [0],
    grid_smargon_mm: tuple[float, float, float] = (-0.614, 0.0259, 0.250),
    rotation_smargon_mm: tuple[float, float, float] = (-0.4634, 0.0187, 0.2482),
):
    @set_run_key_decorator(CONST.PLAN.ROTATION_MAIN)
    @run_decorator(
        md={
            "subplan_name": CONST.PLAN.ROTATION_MAIN,
        }
    )
    def rotation_plan(rotation_snapshot_dir: Path, chi: float):
        yield from bps.abs_set(oav.snapshot.directory, str(rotation_snapshot_dir))
        for _omega in (
            0,
            270,
        ):
            yield from bps.create(DocDescriptorNames.OAV_ROTATION_SNAPSHOT_TRIGGERED)
            yield from bps.read(oav)  # Capture path info for generated snapshot
            yield from bps.read(smargon)  # Capture the current sample x, y, z
            yield from bps.save()

    @set_run_key_decorator(CONST.PLAN.LOAD_CENTRE_COLLECT)
    @run_decorator(
        md={
            "activate_callbacks": ["BeamDrawingCallback"],
            "with_snapshot": WithSnapshot.model_validate(
                {
                    "snapshot_directory": snapshot_directory,
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
        yield from bps.mv(
            smargon.x,
            grid_smargon_mm[0],
            smargon.y,
            grid_smargon_mm[1],
            smargon.z,
            grid_smargon_mm[2],
        )
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
        yield from bps.mv(
            smargon.x,
            rotation_smargon_mm[0],
            smargon.y,
            rotation_smargon_mm[1],
            smargon.z,
            rotation_smargon_mm[2],
        )
        yield from bps.wait()
        for chi in chis:
            yield from rotation_plan(rotation_snapshot_dir, chi)

    yield from inner()


class TestGeneratedSnapshots:
    @pytest.fixture()
    def next_snapshot(self, request: FixtureRequest):
        return MagicMock(side_effect=request.param)

    @pytest.fixture()
    def test_config_files(self):
        return {
            "zoom_params_file": "tests/test_data/test_jCameraManZoomLevels.xml",
            "oav_config_json": "tests/test_data/test_daq_configuration/OAVCentring_hyperion.json",
            "display_config": "tests/test_data/test_daq_configuration/display.configuration",
        }

    @pytest.fixture()
    def snapshot_oav_with_1x_zoom(self, oav_with_snapshots):
        set_mock_value(oav_with_snapshots.zoom_controller.level, "1.0x")
        return oav_with_snapshots

    @pytest.mark.parametrize("chis", [[0], [0, 30]])
    @pytest.mark.parametrize(
        "next_snapshot, expected_0_img, expected_270_img, grid_smargon_mm, "
        "rotation_smargon_mm",
        [
            [
                [
                    "tests/test_data/test_images/thau_1_91_0.png",
                    "tests/test_data/test_images/thau_1_91_90.png",
                ],
                "thau_1_91_expected_0.png",
                "thau_1_91_expected_270.png",
                (-0.614, 0.0259, 0.250),
                (-0.4634, 0.0187, 0.2482),
            ],
            [
                [
                    "tests/test_data/test_images/thau_1_91_0.png",
                    "tests/test_data/test_images/thau_1_91_90.png",
                ],
                "thau_1_91_expected_0.png",
                "thau_1_91_expected_270.png",
                (-0.614, 0.0259, 0.250),
                (-0.4634, 0.0187, 0.2482),
            ],
            [
                [
                    "tests/test_data/test_images/ins_15_33_0.png",
                    "tests/test_data/test_images/ins_15_33_90.png",
                ],
                "ins_15_33_expected_0.png",
                "ins_15_33_expected_270.png",
                (0.4678, -0.5481, -0.3128),
                (0.335, -0.532, -0.243),
            ],
        ],
        indirect=["next_snapshot"],
    )
    def test_snapshot_callback_generate_snapshot_from_gridscan(
        self,
        tmp_path: Path,
        RE: RunEngine,
        snapshot_oav_with_1x_zoom: OAV,
        smargon: Smargon,
        chis: Sequence[int],
        expected_0_img: str,
        expected_270_img: str,
        grid_smargon_mm: tuple[float, float, float],
        rotation_smargon_mm: tuple[float, float, float],
    ):
        downstream_cb = Mock()
        callback = BeamDrawingCallback(emit=downstream_cb)

        RE.subscribe(callback)
        RE(
            simple_take_grid_snapshot_and_generate_rotation_snapshot_plan(
                snapshot_oav_with_1x_zoom,
                smargon,
                tmp_path,
                chis,
                grid_smargon_mm,
                rotation_smargon_mm,
            )
        )

        downstream_calls = downstream_cb.mock_calls
        descriptors_to_event_names = {
            c.args[1]["uid"]: c.args[1]["name"]
            for c in downstream_calls
            if c.args[0] == "descriptor"
        }
        rotation_snapshot_events = [
            c.args[1]["data"]
            for c in downstream_calls
            if c.args[0] == "event"
            and descriptors_to_event_names.get(c.args[1]["descriptor"])
            == DocDescriptorNames.OAV_ROTATION_SNAPSHOT_TRIGGERED
        ]

        i = 0
        for _chi in chis:
            for _omega, expected_image_path in zip(
                [0, 270],
                [
                    f"tests/test_data/test_images/{expected_0_img}",
                    f"tests/test_data/test_images/{expected_270_img}",
                ],
                strict=False,
            ):
                generated_image_path = rotation_snapshot_events[i][
                    "oav-snapshot-last_saved_path"
                ]
                assert_images_pixelwise_equal(
                    generated_image_path,
                    expected_image_path,
                )
                i += 1

    @pytest.mark.parametrize(
        "next_snapshot",
        [
            [
                "tests/test_data/test_images/thau_1_91_0.png",
                "tests/test_data/test_images/thau_1_91_90.png",
            ]
        ],
        indirect=True,
    )
    @pytest.mark.parametrize(
        "expected_px_1, expected_px_2, grid_smargon_mm, rotation_smargon_mm",
        [
            [(397.0, 373.0), (397.0, 373.0), (0, 0, 0), (0, 0, 0)],
            [(497.0, 373.0), (497.0, 373.0), (0, 0, 0), (0.287, 0, 0)],
            [(397.0, 473.0), (397.0, 373.0), (0, 0, 0), (0, 0.287, 0)],
            [(397.0, 373.0), (397.0, 473.0), (0, 0, 0), (0, 0, 0.287)],
        ],
    )
    @patch(
        "mx_bluesky.hyperion.external_interaction.callbacks.snapshot_callback.draw_crosshair"
    )
    def test_draw_crosshair_in_expected_position(
        self,
        mock_draw_crosshair,
        snapshot_oav_with_1x_zoom,
        smargon,
        tmp_path,
        RE,
        expected_px_1,
        expected_px_2,
        grid_smargon_mm,
        rotation_smargon_mm,
    ):
        callback = BeamDrawingCallback()

        RE.subscribe(callback)
        RE(
            simple_take_grid_snapshot_and_generate_rotation_snapshot_plan(
                snapshot_oav_with_1x_zoom,
                smargon,
                tmp_path,
                [0],
                grid_smargon_mm,
                rotation_smargon_mm,
            )
        )

        mock_draw_crosshair.assert_has_calls(
            [
                call(ANY, expected_px_1[0], expected_px_1[1]),
                call(ANY, expected_px_2[0], expected_px_2[1]),
            ]
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
