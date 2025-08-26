from functools import partial
from unittest.mock import MagicMock, patch

import pytest
from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp
from bluesky.run_engine import RunEngine
from dodal.devices.backlight import Backlight
from dodal.devices.robot import BartRobot
from ophyd_async.testing import set_mock_value

from mx_bluesky.common.external_interaction.alerting import Metadata
from mx_bluesky.hyperion.experiment_plans.robot_load_and_change_energy import (
    robot_load_and_snapshots,
)
from mx_bluesky.hyperion.external_interaction.callbacks.alert_on_container_change import (
    AlertOnContainerChange,
)
from mx_bluesky.hyperion.parameters.constants import CONST

TEST_SAMPLE_ID = 10
TEST_VISIT = "cm1234-67"


def wrap_plan(container: int, plan):
    yield from bpp.run_wrapper(
        plan(),
        md={
            "metadata": {
                "container": container,
                "sample_id": TEST_SAMPLE_ID,
                "visit": TEST_VISIT,
            },
            "activate_callbacks": ["AlertOnContainerChange"],
        },
    )


def dummy_plan_with_container(robot: BartRobot, container: int):
    def my_plan():
        yield from bps.create(name=CONST.DESCRIPTORS.ROBOT_PRE_LOAD)
        yield from bps.read(robot)
        yield from bps.save()

    yield from wrap_plan(container, my_plan)


@patch.dict("os.environ", {"BEAMLINE": "i03"})
def test_when_data_collected_on_the_same_container_then_only_alerts_for_first_one(
    RE: RunEngine, mock_alert_service: MagicMock, robot: BartRobot
):
    RE.subscribe(AlertOnContainerChange())

    set_mock_value(robot.current_puck, 5)

    RE(dummy_plan_with_container(robot, 5))
    RE(dummy_plan_with_container(robot, 5))
    RE(dummy_plan_with_container(robot, 5))

    mock_alert_service.raise_alert.assert_not_called()


@patch.dict("os.environ", {"BEAMLINE": "i03"})
def test_when_data_collected_on_new_container_then_only_alerts(
    RE: RunEngine,
    mock_alert_service: MagicMock,
    robot: BartRobot,
):
    RE.subscribe(AlertOnContainerChange())
    set_mock_value(robot.current_puck, 5)

    RE(dummy_plan_with_container(robot, 10))

    mock_alert_service.raise_alert.assert_called_once_with(
        "UDC moved on to puck 10 on i03",
        "Hyperion finished container 5 and moved on to 10",
        {
            Metadata.SAMPLE_ID: "10",
            Metadata.VISIT: "cm1234-67",
            Metadata.CONTAINER: "10",
        },
    )


@patch.dict("os.environ", {"BEAMLINE": "i03"})
@patch(
    "mx_bluesky.hyperion.experiment_plans.robot_load_and_change_energy.do_robot_load"
)
def test_robot_load_and_snapshots_triggers_alert(
    patched_robot_load: MagicMock,
    RE: RunEngine,
    mock_alert_service: MagicMock,
    robot: BartRobot,
    backlight: Backlight,
):
    RE.subscribe(AlertOnContainerChange())
    set_mock_value(robot.current_puck, 5)

    mock_composite = MagicMock()
    mock_composite.robot = robot
    mock_composite.backlight = backlight

    patched_robot_load.side_effect = NotImplementedError()

    with pytest.raises(NotImplementedError):
        RE(
            wrap_plan(
                10,
                partial(
                    robot_load_and_snapshots,
                    mock_composite,
                    MagicMock(),
                    MagicMock(),
                    1,
                    2,
                    None,
                ),
            )
        )

    mock_alert_service.raise_alert.assert_called_once_with(
        "UDC moved on to puck 10 on i03",
        "Hyperion finished container 5 and moved on to 10",
        {
            Metadata.SAMPLE_ID: "10",
            Metadata.VISIT: "cm1234-67",
            Metadata.CONTAINER: "10",
        },
    )
