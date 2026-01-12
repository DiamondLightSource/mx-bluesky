from pathlib import Path
from unittest.mock import patch

import pytest
from blueapi.config import ApplicationConfig
from blueapi.core import BlueskyContext
from blueapi.worker import Task
from bluesky import RunEngine

from .conftest import raw_params_from_file


@pytest.fixture
def bluesky_context(run_engine: RunEngine):
    config = ApplicationConfig(
        **{
            "env": {
                "sources": [
                    {
                        "kind": "deviceManager",
                        "module": "dodal.beamlines.i03",
                        "mock": True,
                    },
                    {
                        "kind": "planFunctions",
                        "module": "mx_bluesky.hyperion.blueapi_plans",
                    },
                ]
            }
        }
    )
    yield BlueskyContext(run_engine=run_engine, configuration=config)


def test_load_centre_collect(bluesky_context: BlueskyContext, tmp_path: Path):
    params = raw_params_from_file(
        "tests/test_data/parameter_json_files/good_test_load_centre_collect_params.json",
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


def _call_blueapi_plan(
    bluesky_context: BlueskyContext,
    plan_name: str,
    internal_name: str,
    parameters: dict,
):
    with patch(
        f"mx_bluesky.hyperion.blueapi_plans.{internal_name}",
        return_value=iter([]),
        create=False,
    ) as mock_plan:
        Task(name=plan_name, params=parameters).do_task(bluesky_context)

    mock_plan.assert_called_once()
