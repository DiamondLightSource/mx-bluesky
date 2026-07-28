from pathlib import Path
from unittest.mock import patch

import pytest
from blueapi.config import ApplicationConfig
from blueapi.core import BlueskyContext
from blueapi.worker import Task
from bluesky import RunEngine
from dodal.devices.robot import BartRobot
from ophyd_async.core import set_mock_value

from mx_bluesky.hyperion.parameters.gridscan import PinTipCentreThenXrayCentre

from .conftest import raw_params_from_file


@pytest.fixture
def bluesky_context(run_engine: RunEngine, use_beamline_i03):
    config = ApplicationConfig(
        **{  # type: ignore
            "env": {
                "sources": [
                    {
                        "kind": "deviceManager",
                        "module": "dodal.beamlines.i03",
                        "mock": True,
                    },
                    {
                        "kind": "planFunctions",
                        "module": "mx_bluesky.hyperion.blueapi.plans",
                    },
                ]
            }
        }
    )
    yield BlueskyContext(run_engine=run_engine, configuration=config)


def test_load_centre_collect(bluesky_context: BlueskyContext, tmp_path: Path):
    params = raw_params_from_file(
        "tests/test_data/parameter_json_files/external_load_centre_collect_params.json",
        tmp_path,
    )
    _call_blueapi_plan(
        bluesky_context,
        "load_centre_collect",
        "_load_centre_collect_full",
        {"parameters": params},
    )


def test_robot_unload(bluesky_context: BlueskyContext, tmp_path: Path):
    _call_blueapi_plan(
        bluesky_context, "robot_unload", "_robot_unload", {"visit": "cm12345-67"}
    )


def test_move_to_udc_default_state(bluesky_context: BlueskyContext):
    _call_blueapi_plan(
        bluesky_context, "move_to_udc_default_state", "_move_to_udc_default_state", {}
    )


def test_pin_tip_centre_then_xray_centre(
    bluesky_context: BlueskyContext, tmp_path: Path
):
    robot: BartRobot = bluesky_context.find_device("robot")  # type: ignore
    set_mock_value(robot.sample_id, 123456)
    set_mock_value(robot.current_puck, 5)
    set_mock_value(robot.current_pin, 15)
    mock_plan = _call_blueapi_plan(
        bluesky_context,
        "pin_tip_centre_then_xray_centre",
        "_pin_tip_centre_then_xray_centre",
        {"visit": "cm12345-67", "storage_directory": str(tmp_path)},
        patch_package="mx_bluesky.hyperion.blueapi.plans",
    )
    params: PinTipCentreThenXrayCentre = mock_plan.mock_calls[0].args[1]
    assert params.visit == "cm12345-67"
    assert params.storage_directory == str(tmp_path)
    assert params.sample_id == 123456
    assert params.sample_puck == 5
    assert params.sample_pin == 15


def _call_blueapi_plan(
    bluesky_context: BlueskyContext,
    plan_name: str,
    internal_name: str,
    parameters: dict,
    patch_package: str = "mx_bluesky.hyperion.blueapi.in_process",
):
    with patch(
        f"{patch_package}.{internal_name}",
        return_value=iter([]),
        create=False,
    ) as mock_plan:
        Task(name=plan_name, params=parameters).do_task(bluesky_context)

    mock_plan.assert_called_once()
    return mock_plan
