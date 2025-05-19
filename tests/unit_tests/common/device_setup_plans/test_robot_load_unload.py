from unittest.mock import ANY, MagicMock, patch

import pytest
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from bluesky.utils import Msg
from dodal.devices.aperturescatterguard import ApertureScatterguard, ApertureValue
from dodal.devices.motors import XYZPositioner
from dodal.devices.robot import BartRobot
from dodal.devices.smargon import Smargon, StubPosition
from ophyd_async.testing import get_mock_put, set_mock_value

from mx_bluesky.common.device_setup_plans.robot_load_unload import (
    prepare_for_robot_load,
    robot_unload,
)
from mx_bluesky.hyperion.external_interaction.callbacks.robot_actions.ispyb_callback import (
    RobotLoadISPyBCallback,
)


async def test_when_prepare_for_robot_load_called_then_moves_as_expected(
    aperture_scatterguard: ApertureScatterguard, smargon: Smargon, done_status
):
    smargon.stub_offsets.set = MagicMock(return_value=done_status)
    get_mock_put(aperture_scatterguard.selected_aperture).reset_mock()

    set_mock_value(smargon.x.user_setpoint, 10)
    set_mock_value(smargon.z.user_setpoint, 5)
    set_mock_value(smargon.omega.user_setpoint, 90)

    RE = RunEngine()
    RE(prepare_for_robot_load(aperture_scatterguard, smargon))

    assert await smargon.x.user_setpoint.get_value() == 0
    assert await smargon.z.user_setpoint.get_value() == 0
    assert await smargon.omega.user_setpoint.get_value() == 0

    smargon.stub_offsets.set.assert_called_once_with(StubPosition.RESET_TO_ROBOT_LOAD)  # type: ignore
    get_mock_put(aperture_scatterguard.selected_aperture).assert_called_once_with(
        ApertureValue.OUT_OF_BEAM, wait=ANY
    )


async def test_when_robot_unload_called_then_sample_area_prepared_before_load(
    robot: BartRobot,
    smargon: Smargon,
    aperture_scatterguard: ApertureScatterguard,
    lower_gonio: XYZPositioner,
    sim_run_engine: RunEngineSimulator,
):
    msgs = sim_run_engine.simulate_plan(
        robot_unload(robot, smargon, aperture_scatterguard, lower_gonio, "")
    )

    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == aperture_scatterguard.selected_aperture.name
        and msg.args[0] == ApertureValue.OUT_OF_BEAM,
    )

    for axis in ["x", "y", "z", "omega", "chi", "phi"]:
        msgs = assert_message_and_return_remaining(
            msgs,
            lambda msg: msg.command == "set"
            and msg.obj.name == f"smargon-{axis}"
            and msg.args[0] == 0,
        )

    assert_message_and_return_remaining(
        msgs, lambda msg: msg.command == "trigger" and msg.obj.name == robot.unload.name
    )


@patch(
    "mx_bluesky.common.device_setup_plans.robot_load_unload.wait_for_smargon_not_disabled",
    return_value=iter([Msg(command="wait_for_smargon")]),
)
async def test_given_lower_gonio_needs_moving_then_it_is_homed_before_unload_and_put_back_after(
    robot: BartRobot,
    smargon: Smargon,
    aperture_scatterguard: ApertureScatterguard,
    lower_gonio: XYZPositioner,
    sim_run_engine: RunEngineSimulator,
):
    # Replace when https://github.com/bluesky/bluesky/issues/1906 is fixed
    def locate_gonio(_):
        return {"readback": 0.1}

    sim_run_engine.add_handler("locate", locate_gonio, lower_gonio.x.name)
    sim_run_engine.add_handler("locate", locate_gonio, lower_gonio.y.name)
    sim_run_engine.add_handler("locate", locate_gonio, lower_gonio.z.name)

    msgs = sim_run_engine.simulate_plan(
        robot_unload(robot, smargon, aperture_scatterguard, lower_gonio, "")
    )

    for axis in ["x", "y", "z"]:
        msgs = assert_message_and_return_remaining(
            msgs,
            lambda msg: msg.command == "set"
            and msg.obj.name == f"lower_gonio-{axis}"
            and msg.args[0] == 0,
        )

    msgs = assert_message_and_return_remaining(
        msgs, lambda msg: msg.command == "trigger" and msg.obj.name == robot.unload.name
    )

    msgs = assert_message_and_return_remaining(
        msgs, lambda msg: msg.command == "wait_for_smargon"
    )

    for axis in ["x", "y", "z"]:
        msgs = assert_message_and_return_remaining(
            msgs,
            lambda msg: msg.command == "set"
            and msg.obj.name == f"lower_gonio-{axis}"
            and msg.args[0] == 0.1,
        )


def test_when_unload_plan_run_then_initial_unload_ispyb_deposition_made(
    RE: RunEngine,
    robot: BartRobot,
    smargon: Smargon,
    aperture_scatterguard: ApertureScatterguard,
    lower_gonio: XYZPositioner,
):
    callback = RobotLoadISPyBCallback()
    callback.expeye = (mock_expeye := MagicMock())
    RE.subscribe(callback)

    set_mock_value(robot.sample_id, expected_sample_id := 1234)

    RE(robot_unload(robot, smargon, aperture_scatterguard, lower_gonio, "cm37235-2"))

    mock_expeye.start_robot_action.assert_called_once_with(
        "UNLOAD", "cm37235", 2, expected_sample_id
    )


def test_when_unload_plan_run_then_full_ispyb_deposition_made(
    RE: RunEngine,
    robot: BartRobot,
    smargon: Smargon,
    aperture_scatterguard: ApertureScatterguard,
    lower_gonio: XYZPositioner,
):
    callback = RobotLoadISPyBCallback()
    callback.expeye = (mock_expeye := MagicMock())
    RE.subscribe(callback)

    set_mock_value(robot.sample_id, expected_sample_id := 1234)
    set_mock_value(robot.current_pin, expected_pin := 12)
    set_mock_value(robot.current_puck, expected_puck := 45)
    set_mock_value(robot.barcode, expected_barcode := "BARCODE")

    action_id = 1098
    mock_expeye.start_robot_action.return_value = action_id

    RE(robot_unload(robot, smargon, aperture_scatterguard, lower_gonio, "cm37235-2"))

    mock_expeye.start_robot_action.assert_called_once_with(
        "UNLOAD", "cm37235", 2, expected_sample_id
    )
    mock_expeye.update_robot_action.assert_called_once_with(
        action_id,
        {
            "sampleBarcode": expected_barcode,
            "containerLocation": expected_pin,
            "dewarLocation": expected_puck,
        },
    )
    mock_expeye.end_robot_action.assert_called_once_with(action_id, "success", "OK")


@patch(
    "mx_bluesky.common.device_setup_plans.robot_load_unload.wait_for_smargon_not_disabled"
)
def test_when_unload_plan_fails_then_error_deposited_in_ispyb(
    mock_wait_for_smargon: MagicMock,
    RE: RunEngine,
    robot: BartRobot,
    smargon: Smargon,
    aperture_scatterguard: ApertureScatterguard,
    lower_gonio: XYZPositioner,
):
    class TestException(Exception): ...

    callback = RobotLoadISPyBCallback()
    callback.expeye = (mock_expeye := MagicMock())
    RE.subscribe(callback)
    mock_wait_for_smargon.side_effect = TestException("Bad Error")

    action_id = 1098
    mock_expeye.start_robot_action.return_value = action_id

    with pytest.raises(TestException):
        RE(
            robot_unload(
                robot, smargon, aperture_scatterguard, lower_gonio, "cm37235-2"
            )
        )

    mock_expeye.start_robot_action.assert_called_once_with("UNLOAD", "cm37235", 2, ANY)
    mock_expeye.end_robot_action.assert_called_once_with(action_id, "fail", "Bad Error")
