from unittest.mock import MagicMock, patch

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
import pytest
from bluesky.run_engine import RunEngine
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.robot import BartRobot
from dodal.devices.webcam import Webcam
from ophyd_async.testing import set_mock_value

from mx_bluesky.common.external_interaction.ispyb.exp_eye_store import BLSampleStatus
from mx_bluesky.hyperion.external_interaction.callbacks.robot_load.ispyb_callback import (
    RobotLoadISPyBCallback,
)
from mx_bluesky.hyperion.parameters.constants import CONST

VISIT = "cm31105-4"

SAMPLE_ID = 231412
SAMPLE_PUCK = 50
SAMPLE_PIN = 4
ACTION_ID = 1098

metadata = {
    "subplan_name": CONST.PLAN.ROBOT_LOAD,
    "metadata": {
        "visit": VISIT,
        "sample_id": SAMPLE_ID,
        "sample_puck": SAMPLE_PUCK,
        "sample_pin": SAMPLE_PIN,
    },
    "activate_callbacks": [
        "RobotLoadISPyBCallback",
    ],
}


@patch(
    "mx_bluesky.hyperion.external_interaction.callbacks.robot_load.ispyb_callback.ExpeyeInteraction",
    autospec=True,
)
def test_given_start_doc_with_expected_data_then_data_put_in_ispyb(
    expeye: MagicMock,
):
    RE = RunEngine()
    RE.subscribe(RobotLoadISPyBCallback())
    expeye.return_value.start_load.return_value = ACTION_ID

    @bpp.run_decorator(md=metadata)
    def my_plan():
        yield from bps.null()

    RE(my_plan())

    expeye.return_value.start_load.assert_called_once_with(
        "cm31105", 4, SAMPLE_ID, SAMPLE_PUCK, SAMPLE_PIN
    )
    expeye.return_value.end_load.assert_called_once_with(ACTION_ID, "success", "OK")


@patch(
    "mx_bluesky.hyperion.external_interaction.callbacks.robot_load.ispyb_callback.ExpeyeInteraction",
    autospec=True,
)
def test_given_failing_plan_then_exception_detail(
    expeye: MagicMock,
):
    RE = RunEngine()
    RE.subscribe(RobotLoadISPyBCallback())
    expeye.return_value.start_load.return_value = ACTION_ID

    class _Exception(Exception): ...

    @bpp.run_decorator(md=metadata)
    def my_plan():
        raise _Exception("BAD")
        yield from bps.null()

    with pytest.raises(_Exception):
        RE(my_plan())

    expeye.return_value.start_load.assert_called_once_with(
        "cm31105", 4, SAMPLE_ID, SAMPLE_PUCK, SAMPLE_PIN
    )
    expeye.return_value.end_load.assert_called_once_with(ACTION_ID, "fail", "BAD")


@patch(
    "mx_bluesky.hyperion.external_interaction.callbacks.robot_load.ispyb_callback.ExpeyeInteraction.end_load"
)
@patch(
    "mx_bluesky.hyperion.external_interaction.callbacks.robot_load.ispyb_callback.ExpeyeInteraction"
    ".update_sample_status",
    new=MagicMock(),
)
def test_given_end_called_but_no_start_then_exception_raised(end_load):
    callback = RobotLoadISPyBCallback()
    callback.active = True
    with pytest.raises(AssertionError):
        callback.activity_gated_stop({"run_uid": None})  # type: ignore
    end_load.assert_not_called()


@bpp.run_decorator(md=metadata)
def successful_robot_load_plan(robot: BartRobot, oav: OAV, webcam: Webcam):
    yield from bps.create(name=CONST.DESCRIPTORS.ROBOT_LOAD)
    yield from bps.read(robot.barcode)
    yield from bps.read(oav.snapshot)
    yield from bps.read(webcam)
    yield from bps.save()


@bpp.run_decorator(md=metadata)
def unsuccessful_robot_load_plan():
    yield from []
    raise AssertionError("Test failure")


@patch(
    "mx_bluesky.hyperion.external_interaction.callbacks.robot_load.ispyb_callback.ExpeyeInteraction",
    autospec=True,
)
def test_given_plan_reads_barcode_then_data_put_in_ispyb(
    expeye: MagicMock,
    robot: BartRobot,
    oav: OAV,
    webcam: Webcam,
):
    RE = RunEngine()
    RE.subscribe(RobotLoadISPyBCallback())
    expeye.return_value.start_load.return_value = ACTION_ID

    set_mock_value(oav.snapshot.last_saved_path, "test_oav_snapshot")
    set_mock_value(webcam.last_saved_path, "test_webcam_snapshot")

    RE(successful_robot_load_plan(robot, oav, webcam))

    expeye.return_value.start_load.assert_called_once_with(
        "cm31105", 4, SAMPLE_ID, SAMPLE_PUCK, SAMPLE_PIN
    )
    expeye.return_value.update_barcode_and_snapshots.assert_called_once_with(
        ACTION_ID, "BARCODE", "test_webcam_snapshot", "test_oav_snapshot"
    )
    expeye.return_value.end_load.assert_called_once_with(ACTION_ID, "success", "OK")


@patch(
    "mx_bluesky.hyperion.external_interaction.callbacks.robot_load.ispyb_callback.ExpeyeInteraction",
    autospec=True,
)
def test_robot_load_complete_triggers_bl_sample_status_loaded(
    mock_sample_handling,
    RE: RunEngine,
    robot: BartRobot,
    oav: OAV,
    webcam: Webcam,
):
    RE.subscribe(RobotLoadISPyBCallback())

    RE(successful_robot_load_plan(robot, oav, webcam))

    mock_sample_handling.return_value.update_sample_status.assert_called_with(
        SAMPLE_ID, BLSampleStatus.LOADED
    )


@patch(
    "mx_bluesky.hyperion.external_interaction.callbacks.robot_load.ispyb_callback.ExpeyeInteraction",
    autospec=True,
)
def test_robot_load_fails_triggers_bl_sample_status_error(
    mock_sample_handling,
    RE: RunEngine,
    robot: BartRobot,
    oav: OAV,
    webcam: Webcam,
):
    RE.subscribe(RobotLoadISPyBCallback())

    with pytest.raises(AssertionError, match="Test failure"):
        RE(unsuccessful_robot_load_plan())

    mock_sample_handling.return_value.update_sample_status.assert_called_with(
        SAMPLE_ID, BLSampleStatus.ERROR_BEAMLINE
    )
