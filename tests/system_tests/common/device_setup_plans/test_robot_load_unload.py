from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from bluesky.run_engine import RunEngine
from dodal.devices.aperturescatterguard import ApertureScatterguard
from dodal.devices.motors import XYZStage
from dodal.devices.robot import BartRobot
from dodal.devices.smargon import Smargon
from ophyd_async.testing import set_mock_value
from requests import get
from tests.conftest import SimConstants

from mx_bluesky.common.device_setup_plans.robot_load_unload import robot_unload
from mx_bluesky.hyperion.external_interaction.callbacks.robot_actions.ispyb_callback import (
    RobotLoadISPyBCallback,
)


@pytest.mark.system_test
def test_execute_unload_sample_full(
    run_engine: RunEngine,
    robot: BartRobot,
    smargon: Smargon,
    aperture_scatterguard: ApertureScatterguard,
    lower_gonio: XYZStage,
):
    callback = RobotLoadISPyBCallback()
    old_start_robot_action = callback.expeye.start_robot_action
    action_id = None

    def get_robot_action_id(*args, **kwargs):
        nonlocal action_id
        action_id = old_start_robot_action(*args, **kwargs)
        return action_id

    callback.expeye.start_robot_action = MagicMock(side_effect=get_robot_action_id)

    set_mock_value(robot.sample_id, SimConstants.ST_SAMPLE_ID)
    set_mock_value(robot.current_puck, 10)

    run_engine.subscribe(callback)
    run_engine(
        robot_unload(
            robot, smargon, aperture_scatterguard, lower_gonio, SimConstants.ST_VISIT
        )
    )
    get_robot_data_url = f"{callback.expeye._base_url}/robot-actions/{action_id}"
    response = get(get_robot_data_url, auth=callback.expeye._auth)

    assert response.ok
    response = response.json()
    assert response["robotActionId"] == action_id
    assert response["status"] == "SUCCESS"
    assert response["sampleId"] == SimConstants.ST_SAMPLE_ID
    assert response["dewarLocation"] == 10
    assert response["actionType"] == "UNLOAD"
    assert response["message"] == "OK"
