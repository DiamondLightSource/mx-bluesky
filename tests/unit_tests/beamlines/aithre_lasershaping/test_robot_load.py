from pathlib import Path
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import bluesky.plan_stubs as bps
import pytest
from bluesky.run_engine import RunEngine
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.oav.pin_image_recognition import PinTipDetection
from ophyd_async.core import set_mock_value

from mx_bluesky.beamlines.aithre_lasershaping.experiment_plans.robot_load_plan import (
    RobotLoadComposite,
    _take_robot_snapshots,
    robot_load_and_snapshots_plan,
    robot_unload_plan,
)
from mx_bluesky.beamlines.aithre_lasershaping.parameters.constants import CONST
from mx_bluesky.beamlines.aithre_lasershaping.parameters.robot_load_parameters import (
    AithreRobotLoad,
)
from mx_bluesky.beamlines.aithre_lasershaping.robot_load import (
    robot_load_and_snapshot,
    robot_unload,
)
from mx_bluesky.hyperion.external_interaction.callbacks.robot_actions.ispyb_callback import (
    RobotLoadISPyBCallback,
)

from ....conftest import raw_params_from_file


@pytest.fixture
def robot_load_params(tmp_path):
    params = raw_params_from_file(
        "tests/test_data/parameter_json_files/good_test_robot_load_params.json",
        tmp_path,
    )
    return AithreRobotLoad(**params)


@pytest.fixture
def aithre_robot_load_composite(
    robot,
    aithre_gonio,
    oav,
) -> RobotLoadComposite:
    composite = RobotLoadComposite(
        robot,
        aithre_gonio,
        oav,
        aithre_gonio,
    )
    return composite


@pytest.fixture
def mock_pin_tip(pin_tip: PinTipDetection):
    pin_tip._get_tip_and_edge_data = AsyncMock(retrun_value=pin_tip.INVALID_POSITION)
    return pin_tip


def noop_plan():
    yield from bps.null()


@patch(
    "mx_bluesky.beamlines.aithre_lasershaping.experiment_plans.robot_load_plan.pin_tip_centre_plan",
    side_effect=lambda *args, **kwargs: noop_plan(),
)
@patch(
    "mx_bluesky.hyperion.external_interaction.callbacks.robot_actions.ispyb_callback.ExpeyeInteraction"
)
def test_given_ispyb_callback_attached_when_robot_load_and_snapshots_plan_called_then_ispyb_deposited(
    exp_eye: MagicMock,
    mock_pin_tip_centring_plan,
    mock_pin_tip: PinTipDetection,
    aithre_robot_load_composite: RobotLoadComposite,
    robot_load_params: AithreRobotLoad,
    run_engine: RunEngine,
):
    set_mock_value(
        aithre_robot_load_composite.oav.snapshot.last_saved_path,
        "test_oav_snapshot",
    )
    set_mock_value(aithre_robot_load_composite.robot.barcode, "BARCODE")

    run_engine.subscribe(RobotLoadISPyBCallback())

    action_id = 1098
    exp_eye.return_value.start_robot_action.return_value = action_id

    run_engine(
        robot_load_and_snapshots_plan(
            aithre_robot_load_composite, robot_load_params, mock_pin_tip
        )
    )

    mock_pin_tip_centring_plan.assert_called_once()
    exp_eye.return_value.start_robot_action.assert_called_once_with(
        "LOAD", "cm31105", 4, 12345
    )
    exp_eye.return_value.update_robot_action.assert_called_once_with(
        action_id,
        {
            "sampleBarcode": "BARCODE",
            "xtalSnapshotAfter": "test_oav_snapshot",
            "containerLocation": 3,
            "dewarLocation": 40,
        },
    )
    exp_eye.return_value.end_robot_action.assert_called_once_with(
        action_id, "success", "OK"
    )


@patch(
    "mx_bluesky.beamlines.aithre_lasershaping.experiment_plans.robot_load_plan.datetime"
)
async def test_when_take_snapshots_called_then_filename_and_directory_set_and_device_triggered(
    mock_datetime: MagicMock, oav: OAV, run_engine: RunEngine
):
    test_directory = "TEST"

    mock_datetime.now.return_value.strftime.return_value = "TIME"

    oav.snapshot.trigger = MagicMock(side_effect=oav.snapshot.trigger)

    run_engine(_take_robot_snapshots(oav, Path(test_directory)))

    oav.snapshot.trigger.assert_called_once()
    assert await oav.snapshot.filename.get_value() == "TIME_oav-snapshot_after_load"
    assert await oav.snapshot.directory.get_value() == test_directory


@patch(
    "mx_bluesky.beamlines.aithre_lasershaping.experiment_plans.robot_load_plan._move_gonio_to_home_position",
    autospec=True,
)
async def test_when_robot_unload_called_then_sample_area_prepared_before_load(
    mock_move_gonio,
    aithre_robot_load_composite: RobotLoadComposite,
    robot_load_params: AithreRobotLoad,
    run_engine: RunEngine,
):
    run_engine(robot_unload_plan(aithre_robot_load_composite, robot_load_params))

    mock_move_gonio.assert_called_once()


def test_when_unload_plan_run_then_initial_unload_ispyb_deposition_made(
    aithre_robot_load_composite: RobotLoadComposite,
    robot_load_params: AithreRobotLoad,
    run_engine: RunEngine,
):
    callback = RobotLoadISPyBCallback()
    callback.expeye = (mock_expeye := MagicMock())
    run_engine.subscribe(callback)

    run_engine(robot_unload_plan(aithre_robot_load_composite, robot_load_params))

    mock_expeye.start_robot_action.assert_called_once_with(
        "UNLOAD", "cm31105", 4, 12345
    )


def test_when_unload_plan_run_then_full_ispyb_deposition_made(
    aithre_robot_load_composite: RobotLoadComposite,
    robot_load_params: AithreRobotLoad,
    run_engine: RunEngine,
):
    callback = RobotLoadISPyBCallback()
    callback.expeye = (mock_expeye := MagicMock())
    run_engine.subscribe(callback)

    set_mock_value(
        aithre_robot_load_composite.oav.snapshot.last_saved_path,
        "test_oav_snapshot",
    )
    set_mock_value(aithre_robot_load_composite.robot.current_pin, 3)
    set_mock_value(aithre_robot_load_composite.robot.current_puck, 40)

    action_id = 1098
    mock_expeye.start_robot_action.return_value = action_id

    run_engine(robot_unload_plan(aithre_robot_load_composite, robot_load_params))

    mock_expeye.start_robot_action.assert_called_once_with(
        "UNLOAD", "cm31105", 4, 12345
    )
    mock_expeye.update_robot_action.assert_called_once_with(
        action_id,
        {
            "sampleBarcode": "BARCODE",
            "xtalSnapshotAfter": "test_oav_snapshot",
            "containerLocation": 3,
            "dewarLocation": 40,
        },
    )
    mock_expeye.end_robot_action.assert_called_once_with(action_id, "success", "OK")


@patch(
    "mx_bluesky.beamlines.aithre_lasershaping.experiment_plans.robot_load_plan._move_gonio_to_home_position",
    autospec=True,
)
def test_when_unload_plan_fails_then_error_deposited_in_ispyb(
    mock_move_gonio: MagicMock,
    aithre_robot_load_composite: RobotLoadComposite,
    robot_load_params: AithreRobotLoad,
    run_engine: RunEngine,
):
    class TestError(Exception): ...

    callback = RobotLoadISPyBCallback()
    callback.expeye = (mock_expeye := MagicMock())
    run_engine.subscribe(callback)
    mock_move_gonio.side_effect = TestError("Bad Error")

    action_id = 1098
    mock_expeye.start_robot_action.return_value = action_id

    with pytest.raises(TestError):
        run_engine(robot_unload_plan(aithre_robot_load_composite, robot_load_params))

    mock_expeye.start_robot_action.assert_called_once_with("UNLOAD", "cm31105", 4, ANY)
    mock_expeye.end_robot_action.assert_called_once_with(action_id, "fail", "Bad Error")


@patch(
    "mx_bluesky.beamlines.aithre_lasershaping.experiment_plans.robot_load_plan._robot_load_and_snapshots",
    autospec=True,
)
def test_when_robot_load_and_snapshot_plan_called_correct_plan_called(
    mock_robot_load_and_snapshots,
    aithre_robot_load_composite: RobotLoadComposite,
    robot_load_params: AithreRobotLoad,
    run_engine: RunEngine,
):
    tip_offset = 0
    oav_config = CONST.OAV_CENTRING_FILE
    mock_pin_tip_detection = MagicMock(spec=PinTipDetection)
    run_engine(
        robot_load_and_snapshot(
            aithre_robot_load_composite.robot,
            aithre_robot_load_composite.gonio,
            aithre_robot_load_composite.oav,
            mock_pin_tip_detection,
            tip_offset,
            oav_config,
            robot_load_params.sample_puck,
            robot_load_params.sample_pin,
            robot_load_params.sample_id,
            robot_load_params.visit,
        )
    )

    mock_robot_load_and_snapshots.assert_called_once()


@patch(
    "mx_bluesky.beamlines.aithre_lasershaping.experiment_plans.robot_load_plan._move_gonio_to_home_position",
    autospec=True,
)
def test_when_robot_unload_plan_called_correct_plan_called(
    mock_move_gonio,
    aithre_robot_load_composite: RobotLoadComposite,
    robot_load_params: AithreRobotLoad,
    run_engine: RunEngine,
):
    run_engine(
        robot_unload(
            aithre_robot_load_composite.robot,
            aithre_robot_load_composite.gonio,
            aithre_robot_load_composite.oav,
            robot_load_params.sample_puck,
            robot_load_params.sample_pin,
            robot_load_params.sample_id,
            robot_load_params.visit,
        )
    )

    mock_move_gonio.assert_called_once()
