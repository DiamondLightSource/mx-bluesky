from pathlib import Path
from typing import Any, Literal
from unittest.mock import DEFAULT, AsyncMock, MagicMock, patch

import bluesky.preprocessors as bpp
import numpy as np
import pytest
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from bluesky.utils import Msg
from dodal.beamlines import i03
from dodal.devices.backlight import Backlight
from dodal.devices.oav.oav_detector import OAVConfig
from dodal.devices.oav.oav_parameters import OAVParameters
from dodal.devices.oav.pin_image_recognition import PinTipDetection
from dodal.devices.oav.pin_image_recognition.utils import NONE_VALUE, SampleLocation
from dodal.devices.smargon import Smargon
from numpy._typing._array_like import NDArray
from ophyd_async.testing import set_mock_value

from mx_bluesky.common.experiment_plans.oav_grid_detection_plan import (
    OavGridDetectionComposite,
    get_min_and_max_y_of_pin,
    grid_detection_plan,
)
from mx_bluesky.common.external_interaction.callbacks.common.grid_detection_callback import (
    GridDetectionCallback,
)
from mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback import (
    GridscanISPyBCallback,
    ispyb_activation_wrapper,
)
from mx_bluesky.common.parameters.gridscan import GridCommon, SpecifiedThreeDGridScan
from mx_bluesky.common.utils.exceptions import WarningException

from ...conftest import assert_event


@pytest.fixture
def fake_devices(
    RE: RunEngine,
    smargon: Smargon,
    backlight: Backlight,
    test_config_files: dict[str, str],
):
    params = OAVConfig(
        test_config_files["zoom_params_file"], test_config_files["display_config"]
    )
    oav = i03.oav(connect_immediately=True, mock=True, params=params)
    zoom_levels_list = ["1.0x", "3.0x", "5.0x", "7.5x", "10.0x", "15.0x"]
    oav.zoom_controller._get_allowed_zoom_levels = AsyncMock(
        return_value=zoom_levels_list
    )
    set_mock_value(oav.zoom_controller.level, "5.0x")
    set_mock_value(oav.grid_snapshot.x_size, 1024)
    set_mock_value(oav.grid_snapshot.y_size, 768)

    pin_tip_detection = i03.pin_tip_detection(connect_immediately=True, mock=True)
    pin_tip_detection._get_tip_and_edge_data = AsyncMock(
        return_value=SampleLocation(
            8,
            5,
            np.array([0, 0, 0, 0, 0, 0, 0, 0, 5, 5, 4, 4, 3, 3, 2, 2, 3, 3, 4, 4]),
            np.array([0, 0, 0, 0, 0, 0, 0, 0, 5, 5, 6, 6, 7, 7, 8, 8, 7, 7, 6, 6]),
        )
    )

    with (
        patch(
            "dodal.devices.areadetector.plugins.MJPG.ClientSession.get", autospec=True
        ) as patch_get,
        patch("dodal.devices.areadetector.plugins.MJPG.Image") as mock_image_class,
        patch(
            "dodal.devices.oav.snapshots.snapshot_with_grid.asyncio_save_image"
        ) as mock_save_image,
    ):
        patch_get.return_value.__aenter__.return_value = (mock_response := AsyncMock())
        mock_response.ok = True
        mock_response.read.return_value = b""
        mock_image_class.open.return_value.__aenter__.return_value = b""

        composite = OavGridDetectionComposite(
            backlight=backlight,
            oav=oav,
            smargon=smargon,
            pin_tip_detection=pin_tip_detection,
        )

        yield composite, mock_save_image


def do_grid_and_edge_detect(composite, parameters, tmp_dir):
    yield from grid_detection_plan(
        composite,
        parameters=parameters,
        snapshot_dir=f"{tmp_dir}",
        snapshot_template="test_{angle}",
        grid_width_microns=161.2,
        box_size_um=20,
    )


@patch(
    "dodal.common.beamlines.beamline_utils.active_device_is_same_type",
    lambda a, b: True,
)
@patch("bluesky.plan_stubs.sleep", new=MagicMock())
def test_grid_detection_plan_runs_and_triggers_snapshots(
    RE: RunEngine,
    test_config_files: dict[str, str],
    fake_devices: tuple[OavGridDetectionComposite, MagicMock],
    tmp_path: Path,
):
    params = OAVParameters("loopCentring", test_config_files["oav_config_json"])
    composite, image_save = fake_devices

    composite.oav.grid_snapshot._save_image = (mock_save := AsyncMock())

    RE(bpp.run_wrapper(do_grid_and_edge_detect(composite, params, tmp_path)))

    assert image_save.await_count == 4
    assert mock_save.call_count == 2


@patch(
    "dodal.common.beamlines.beamline_utils.active_device_is_same_type",
    lambda a, b: True,
)
@patch("bluesky.plan_stubs.sleep", new=MagicMock())
async def test_grid_detection_plan_gives_warning_error_if_tip_not_found(
    RE: RunEngine,
    test_config_files: dict[str, str],
    fake_devices: tuple[OavGridDetectionComposite, MagicMock],
    tmp_path: Path,
):
    composite, _ = fake_devices

    set_mock_value(composite.pin_tip_detection.validity_timeout, 0.01)
    composite.pin_tip_detection._get_tip_and_edge_data = AsyncMock(
        return_value=SampleLocation(
            PinTipDetection.INVALID_POSITION[0],
            PinTipDetection.INVALID_POSITION[1],
            np.array([]),
            np.array([]),
        )
    )

    params = OAVParameters("loopCentring", test_config_files["oav_config_json"])

    with pytest.raises(WarningException) as excinfo:
        RE(do_grid_and_edge_detect(composite, params, tmp_path))

    assert "No pin found" in excinfo.value.args[0]


@patch(
    "dodal.common.beamlines.beamline_utils.active_device_is_same_type",
    lambda a, b: True,
)
@patch("bluesky.plan_stubs.sleep", new=MagicMock())
async def test_given_when_grid_detect_then_start_position_as_expected(
    fake_devices: tuple[OavGridDetectionComposite, MagicMock],
    RE: RunEngine,
    test_config_files: dict[str, str],
    tmp_path: Path,
):
    params = OAVParameters("loopCentring", test_config_files["oav_config_json"])
    box_size_um = 0.2
    composite, _ = fake_devices
    microns_per_pixel_y = await composite.oav.microns_per_pixel_y.get_value()
    box_size_y_pixels = box_size_um / microns_per_pixel_y

    grid_param_cb = GridDetectionCallback()
    RE.subscribe(grid_param_cb)

    @bpp.run_decorator()
    def decorated():
        yield from grid_detection_plan(
            composite,
            parameters=params,
            snapshot_dir=f"{tmp_path}",
            snapshot_template="test_{angle}",
            grid_width_microns=161.2,
            box_size_um=box_size_um,
        )

    RE(decorated())

    gridscan_params = grid_param_cb.get_grid_parameters()

    assert gridscan_params["x_start_um"] == pytest.approx(-804, abs=1)
    assert gridscan_params["y_start_um"] == pytest.approx(
        -550 - ((box_size_y_pixels / 2) * microns_per_pixel_y), abs=1
    )
    assert gridscan_params["z_start_um"] == pytest.approx(-550, abs=1)


@patch(
    "dodal.common.beamlines.beamline_utils.active_device_is_same_type",
    lambda a, b: True,
)
@patch("bluesky.plan_stubs.sleep", new=MagicMock())
@patch(
    "mx_bluesky.common.experiment_plans.oav_grid_detection_plan.pre_centring_setup_oav",
    new=MagicMock(),
)
def test_when_grid_detection_plan_run_twice_then_values_do_not_persist_in_callback(
    fake_devices: tuple[OavGridDetectionComposite, MagicMock],
    RE: RunEngine,
    test_config_files: dict[str, str],
    tmp_path: Path,
):
    params = OAVParameters("loopCentring", test_config_files["oav_config_json"])

    composite, _ = fake_devices

    for _ in range(2):
        RE(bpp.run_wrapper(do_grid_and_edge_detect(composite, params, tmp_path)))


@patch(
    "dodal.common.beamlines.beamline_utils.active_device_is_same_type",
    lambda a, b: True,
)
@patch("bluesky.plan_stubs.sleep", new=MagicMock())
async def test_when_grid_detection_plan_run_then_ispyb_callback_gets_correct_values(
    fake_devices: tuple[OavGridDetectionComposite, MagicMock],
    RE: RunEngine,
    test_config_files: dict[str, str],
    test_fgs_params: SpecifiedThreeDGridScan,
    tmp_path: Path,
    dummy_rotation_data_collection_group_info,
):
    params = OAVParameters("loopCentring", test_config_files["oav_config_json"])
    composite, _ = fake_devices
    cb = GridscanISPyBCallback(param_type=GridCommon)
    cb.data_collection_group_info = dummy_rotation_data_collection_group_info
    RE.subscribe(cb)

    with patch.multiple(cb, activity_gated_start=DEFAULT, activity_gated_event=DEFAULT):
        RE(
            ispyb_activation_wrapper(
                do_grid_and_edge_detect(composite, params, tmp_path),
                test_fgs_params,
            )
        )

        assert_event(
            cb.activity_gated_start.mock_calls[0],  # pyright:ignore
            {"activate_callbacks": ["GridscanISPyBCallback"]},
        )
        assert_event(
            cb.activity_gated_event.mock_calls[0],  # pyright: ignore
            {
                "oav-grid_snapshot-top_left_x": 8,
                "oav-grid_snapshot-top_left_y": pytest.approx(-4, abs=1),
                "oav-grid_snapshot-num_boxes_x": 9,
                "oav-grid_snapshot-num_boxes_y": 2,
                "oav-grid_snapshot-box_width": pytest.approx(12, abs=1),
                "oav-microns_per_pixel_x": 1.58,
                "oav-microns_per_pixel_y": 1.58,
                "oav-grid_snapshot-last_path_full_overlay": f"{tmp_path}/test_0_grid_overlay.png",
                "oav-grid_snapshot-last_path_outer": f"{tmp_path}/test_0_outer_overlay.png",
                "oav-grid_snapshot-last_saved_path": f"{tmp_path}/test_0.png",
            },
        )
        assert_event(
            cb.activity_gated_event.mock_calls[1],  # pyright:ignore
            {
                "oav-grid_snapshot-top_left_x": 8,
                "oav-grid_snapshot-top_left_y": 2,
                "oav-grid_snapshot-num_boxes_x": 9,
                "oav-grid_snapshot-num_boxes_y": 1,
                "oav-grid_snapshot-box_width": pytest.approx(12, abs=1),
                "oav-microns_per_pixel_x": 1.58,
                "oav-microns_per_pixel_y": 1.58,
                "oav-grid_snapshot-last_path_full_overlay": f"{tmp_path}/test_90_grid_overlay.png",
                "oav-grid_snapshot-last_path_outer": f"{tmp_path}/test_90_outer_overlay.png",
                "oav-grid_snapshot-last_saved_path": f"{tmp_path}/test_90.png",
            },
        )


@patch(
    "dodal.common.beamlines.beamline_utils.active_device_is_same_type",
    lambda a, b: True,
)
@patch("bluesky.plan_stubs.sleep", new=MagicMock())
def test_when_grid_detection_plan_run_then_grid_detection_callback_gets_correct_values(
    fake_devices: tuple[OavGridDetectionComposite, MagicMock],
    RE: RunEngine,
    test_config_files: dict[str, str],
    test_fgs_params: SpecifiedThreeDGridScan,
    tmp_path: Path,
):
    params = OAVParameters("loopCentring", test_config_files["oav_config_json"])
    composite, _ = fake_devices
    box_size_um = 20
    cb = GridDetectionCallback()
    RE.subscribe(cb)

    RE(
        ispyb_activation_wrapper(
            do_grid_and_edge_detect(composite, params, tmp_path), test_fgs_params
        )
    )

    my_grid_params = cb.get_grid_parameters()

    assert my_grid_params["x_start_um"] == pytest.approx(-794.22)
    assert my_grid_params["y_start_um"] == pytest.approx(-539.84 - (box_size_um / 2))
    assert my_grid_params["y2_start_um"] == pytest.approx(-539.84 - (box_size_um / 2))
    assert my_grid_params["z_start_um"] == pytest.approx(-539.84)
    assert my_grid_params["z2_start_um"] == pytest.approx(-539.84)
    assert my_grid_params["x_step_size_um"] == box_size_um
    assert my_grid_params["y_step_size_um"] == box_size_um
    assert my_grid_params["z_step_size_um"] == box_size_um
    assert my_grid_params["x_steps"] == pytest.approx(9)
    assert my_grid_params["y_steps"] == pytest.approx(2)
    assert my_grid_params["z_steps"] == pytest.approx(1)
    assert cb.x_step_size_um == cb.y_step_size_um == cb.z_step_size_um == box_size_um


@pytest.mark.parametrize(
    "odd",
    [(True), (False)],
)
@patch(
    "dodal.common.beamlines.beamline_utils.active_device_is_same_type",
    lambda a, b: True,
)
@patch("bluesky.plan_stubs.sleep", new=MagicMock())
@patch("mx_bluesky.common.experiment_plans.oav_grid_detection_plan.LOGGER")
async def test_when_detected_grid_has_odd_y_steps_then_add_a_y_step_and_shift_grid(
    fake_logger: MagicMock,
    fake_devices: tuple[OavGridDetectionComposite, MagicMock],
    sim_run_engine: RunEngineSimulator,
    test_config_files: dict[str, str],
    odd: bool,
    tmp_path: Path,
):
    composite, _ = fake_devices
    params = OAVParameters("loopCentring", test_config_files["oav_config_json"])
    box_size_um = 20
    microns_per_pixel_y = await composite.oav.microns_per_pixel_y.get_value()
    assert microns_per_pixel_y is not None
    box_size_y_pixels = box_size_um / microns_per_pixel_y
    initial_min_y = 1

    abs_sets: dict[str, list] = {
        "grid_snapshot.top_left_y": [],
        "grid_snapshot.num_boxes_y": [],
    }

    def handle_read(msg: Msg):
        if msg.obj.name == "pin_tip_detection-triggered_tip":
            return {"values": {"value": (8, 5)}}
        if msg.obj.name == "pin_tip_detection-triggered_top_edge":
            top_edge = [0] * 20
            top_edge[19] = initial_min_y
            return {"values": {"value": top_edge}}
        elif msg.obj.name == "pin_tip_detection-triggered_bottom_edge":
            bottom_edge = [0] * 20
            bottom_edge[19] = (
                10 if odd else 25
            )  # Ensure y steps comes out as even or odd
            return {"values": {"value": bottom_edge}}
        else:
            pass

    def record_set(msg: Msg):
        if hasattr(msg.obj, "dotted_name"):
            if msg.obj.dotted_name in abs_sets.keys():
                abs_sets[msg.obj.dotted_name].append(msg.args[0])

    sim_run_engine.add_handler("set", record_set)
    sim_run_engine.add_handler("read", handle_read)
    sim_run_engine.add_read_handler_for(composite.oav.microns_per_pixel_x, 1.58)
    sim_run_engine.add_read_handler_for(composite.oav.microns_per_pixel_y, 1.58)

    msgs = sim_run_engine.simulate_plan(
        do_grid_and_edge_detect(composite, params, tmp_path)
    )

    expected_min_y = initial_min_y - box_size_y_pixels / 2 if odd else initial_min_y
    expected_y_steps = 2

    if odd:
        fake_logger.debug.assert_called_once_with(
            f"Forcing number of rows in first grid to be even: Adding an extra row onto bottom of first grid and shifting grid upwards by {box_size_y_pixels / 2}"
        )
    else:
        fake_logger.debug.assert_not_called()

    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "oav-grid_snapshot-top_left_y"
        and msg.args == (expected_min_y,),
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "oav-grid_snapshot-num_boxes_y"
        and msg.args == (expected_y_steps,),
    )


@pytest.mark.parametrize(
    "top, bottom, expected_min, expected_max",
    [
        (np.array([1, 2, 5]), np.array([8, 9, 40]), 1, 40),
        (np.array([9, 6, 10]), np.array([152, 985, 72]), 6, 985),
        (np.array([5, 1]), np.array([999, 1056, 896, 10]), 1, 1056),
    ],
)
def test_given_array_with_valid_top_and_bottom_then_min_and_max_as_expected(
    top: NDArray[Any],
    bottom: NDArray[Any],
    expected_min: Literal[1] | Literal[6],
    expected_max: Literal[40] | Literal[985] | Literal[1056],
):
    min_y, max_y = get_min_and_max_y_of_pin(top, bottom, 100)
    assert min_y == expected_min
    assert max_y == expected_max


@pytest.mark.parametrize(
    "top, bottom, expected_min, expected_max",
    [
        (np.array([1, 2, NONE_VALUE]), np.array([8, 9, 40]), 1, 40),
        (np.array([6, NONE_VALUE, 10]), np.array([152, 985, NONE_VALUE]), 6, 985),
        (np.array([1, 5]), np.array([999, 1056, NONE_VALUE, 10]), 1, 1056),
    ],
)
def test_given_array_with_some_invalid_top_and_bottom_sections_then_min_and_max_as_expected(
    top: NDArray[Any],
    bottom: NDArray[Any],
    expected_min: Literal[1] | Literal[6],
    expected_max: Literal[40] | Literal[985] | Literal[1056],
):
    min_y, max_y = get_min_and_max_y_of_pin(top, bottom, 100)
    assert min_y == expected_min
    assert max_y == expected_max


@pytest.mark.parametrize(
    "top, bottom, expected_min, expected_max",
    [
        (np.array([NONE_VALUE, 0, NONE_VALUE]), np.array([100, NONE_VALUE]), 0, 100),
        (np.array([NONE_VALUE, NONE_VALUE]), np.array([100, NONE_VALUE]), 0, 100),
        (np.array([0, NONE_VALUE]), np.array([NONE_VALUE]), 0, 100),
    ],
)
def test_given_array_with_all_invalid_top_and_bottom_sections_then_min_and_max_is_full_image(
    top: NDArray[Any],
    bottom: NDArray[Any],
    expected_min: Literal[0],
    expected_max: Literal[100],
):
    min_y, max_y = get_min_and_max_y_of_pin(top, bottom, 100)
    assert min_y == expected_min
    assert max_y == expected_max
