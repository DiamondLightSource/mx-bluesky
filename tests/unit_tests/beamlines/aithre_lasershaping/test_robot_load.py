from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from bluesky.run_engine import RunEngine
from dodal.devices.oav.oav_detector import OAV
from ophyd_async.testing import set_mock_value

from mx_bluesky.beamlines.aithre_lasershaping.parameters.robot_load_parameters import (
    AithreRobotLoad,
)
from mx_bluesky.beamlines.aithre_lasershaping.robot_load_plan import (
    RobotLoadComposite,
    robot_load_and_snapshots_plan,
    take_robot_snapshots,
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


@patch(
    "mx_bluesky.hyperion.external_interaction.callbacks.robot_actions.ispyb_callback.ExpeyeInteraction"
)
def test_given_ispyb_callback_attached_when_robot_load_and_snapshots_plan_called_then_ispyb_deposited(
    exp_eye: MagicMock,
    aithre_robot_load_composite: RobotLoadComposite,
    robot_load_params: AithreRobotLoad,
    run_engine: RunEngine,
):
    robot = aithre_robot_load_composite.robot
    set_mock_value(
        aithre_robot_load_composite.oav.snapshot.last_saved_path,
        "test_oav_snapshot",
    )
    set_mock_value(robot.barcode, "BARCODE")

    run_engine.subscribe(RobotLoadISPyBCallback())

    action_id = 1098
    exp_eye.return_value.start_robot_action.return_value = action_id

    run_engine(
        robot_load_and_snapshots_plan(aithre_robot_load_composite, robot_load_params)
    )

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


# Leave for later load and centre plan
"""
@patch(
    "mx_bluesky.hyperion.external_interaction.callbacks.robot_actions.ispyb_callback.ExpeyeInteraction"
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.robot_load_and_change_energy.set_energy_plan",
    MagicMock(return_value=iter([])),
)
def test_given_ispyb_callback_attached_when_robot_load_then_centre_plan_called_then_ispyb_deposited(
    exp_eye: MagicMock,
    robot_load_and_energy_change_composite: RobotLoadAndEnergyChangeComposite,
    robot_load_and_energy_change_params: RobotLoadAndEnergyChange,
    run_engine: RunEngine,
):
    robot = robot_load_and_energy_change_composite.robot
    webcam = robot_load_and_energy_change_composite.webcam
    set_mock_value(
        robot_load_and_energy_change_composite.oav.snapshot.last_saved_path,
        "test_oav_snapshot",
    )
    set_mock_value(webcam.last_saved_path, "test_webcam_snapshot")
    webcam.trigger = MagicMock(return_value=NullStatus())
    set_mock_value(robot.barcode, "BARCODE")

    run_engine.subscribe(RobotLoadISPyBCallback())

    action_id = 1098
    exp_eye.return_value.start_robot_action.return_value = action_id

    run_engine(
        robot_load_and_change_energy_plan(
            robot_load_and_energy_change_composite, robot_load_and_energy_change_params
        )
    )

    exp_eye.return_value.start_robot_action.assert_called_once_with(
        "LOAD", "cm31105", 4, 12345
    )
    exp_eye.return_value.update_robot_action.assert_called_once_with(
        action_id,
        {
            "sampleBarcode": "BARCODE",
            "xtalSnapshotBefore": "test_webcam_snapshot",
            "xtalSnapshotAfter": "test_oav_snapshot",
            "containerLocation": 3,
            "dewarLocation": 40,
        },
    )
    exp_eye.return_value.end_robot_action.assert_called_once_with(
        action_id, "success", "OK"
    )
"""


@patch("mx_bluesky.beamlines.aithre_lasershaping.robot_load_plan.datetime")
async def test_when_take_snapshots_called_then_filename_and_directory_set_and_device_triggered(
    mock_datetime: MagicMock, oav: OAV, run_engine: RunEngine
):
    test_directory = "TEST"

    mock_datetime.now.return_value.strftime.return_value = "TIME"

    oav.snapshot.trigger = MagicMock(side_effect=oav.snapshot.trigger)

    run_engine(take_robot_snapshots(oav, Path(test_directory)))

    oav.snapshot.trigger.assert_called_once()
    assert await oav.snapshot.filename.get_value() == "TIME_oav-snapshot_after_load"
    assert await oav.snapshot.directory.get_value() == test_directory
