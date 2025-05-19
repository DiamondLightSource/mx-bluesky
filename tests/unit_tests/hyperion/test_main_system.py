from __future__ import annotations

import functools
import json
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass
from sys import argv
from time import sleep
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from blueapi.core import BlueskyContext
from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
from dodal.devices.zebra.zebra import Zebra
from flask.testing import FlaskClient

from mx_bluesky.common.utils.context import device_composite_from_context
from mx_bluesky.common.utils.exceptions import WarningException
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.hyperion.__main__ import (
    Actions,
    BlueskyRunner,
    Status,
    create_app,
    setup_context,
)
from mx_bluesky.hyperion.experiment_plans.experiment_registry import PLAN_REGISTRY
from mx_bluesky.hyperion.parameters.cli import parse_cli_args
from mx_bluesky.hyperion.parameters.gridscan import HyperionSpecifiedThreeDGridScan

from ...conftest import raw_params_from_file
from ..conftest import mock_beamline_module_filepaths

FGS_ENDPOINT = "/pin_tip_centre_then_xray_centre/"
START_ENDPOINT = FGS_ENDPOINT + Actions.START.value
STOP_ENDPOINT = Actions.STOP.value
STATUS_ENDPOINT = Actions.STATUS.value
SHUTDOWN_ENDPOINT = Actions.SHUTDOWN.value
TEST_BAD_PARAM_ENDPOINT = "/fgs_real_params/" + Actions.START.value
TEST_PARAMS = json.dumps(
    raw_params_from_file(
        "tests/test_data/parameter_json_files/good_test_pin_centre_then_xray_centre_parameters.json"
    )
)

SECS_PER_RUNENGINE_LOOP = 0.1
RUNENGINE_TAKES_TIME_TIMEOUT = 15

"""
Every test in this file which uses the test_env fixture should either:
    - set RE_takes_time to false
    or
    - set an error on the mock run engine
In order to avoid threads which get left alive forever after test completion
"""


autospec_patch = functools.partial(patch, autospec=True, spec_set=True)


class MockRunEngine:
    def __init__(self, test_name):
        self.RE_takes_time = True
        self.aborting_takes_time = False
        self.error: Exception | None = None
        self.test_name = test_name

    def __call__(self, *args: Any, **kwds: Any) -> Any:
        time = 0.0
        while self.RE_takes_time:
            sleep(SECS_PER_RUNENGINE_LOOP)
            time += SECS_PER_RUNENGINE_LOOP
            if self.error:
                raise self.error
            if time > RUNENGINE_TAKES_TIME_TIMEOUT:
                raise TimeoutError(
                    f'Mock RunEngine thread for test "{self.test_name}" spun too long'
                    "without an error. Most likely you should initialise with "
                    "RE_takes_time=false, or set RE.error from another thread."
                )
        if self.error:
            raise self.error

    def abort(self):
        while self.aborting_takes_time:
            sleep(SECS_PER_RUNENGINE_LOOP)
            if self.error:
                raise self.error
        self.RE_takes_time = False

    def subscribe(self, *args):
        pass

    def unsubscribe(self, *args):
        pass


@dataclass
class ClientAndRunEngine:
    client: FlaskClient
    mock_run_engine: MockRunEngine


def mock_dict_values(d: dict):
    return {k: MagicMock() if k == "setup" or k == "run" else v for k, v in d.items()}


TEST_EXPTS = {
    "test_experiment": {
        "setup": MagicMock(),
        "param_type": MagicMock(),
    },
    "fgs_real_params": {
        "setup": MagicMock(),
        "param_type": HyperionSpecifiedThreeDGridScan,
    },
}


@pytest.fixture
def test_env(request: pytest.FixtureRequest):
    mock_run_engine = MockRunEngine(test_name=repr(request))
    mock_context = BlueskyContext()
    real_plans_and_test_exps = dict(
        {k: mock_dict_values(v) for k, v in PLAN_REGISTRY.items()},  # type: ignore
        **TEST_EXPTS,  # type: ignore
    )
    mock_context.plan_functions = {  # type: ignore
        k: MagicMock() for k in real_plans_and_test_exps.keys()
    }

    with (
        patch.dict(
            "mx_bluesky.hyperion.__main__.PLAN_REGISTRY",
            real_plans_and_test_exps,
        ),
        patch(
            "mx_bluesky.hyperion.__main__.setup_context",
            MagicMock(return_value=mock_context),
        ),
    ):
        app, runner = create_app({"TESTING": True}, mock_run_engine)  # type: ignore

    runner_thread = threading.Thread(target=runner.wait_on_queue)
    runner_thread.start()
    with (
        app.test_client() as client,
        patch.dict(
            "mx_bluesky.hyperion.__main__.PLAN_REGISTRY",
            real_plans_and_test_exps,
        ),
    ):
        yield ClientAndRunEngine(client, mock_run_engine)

    runner.shutdown()
    runner_thread.join(timeout=3)
    del mock_run_engine


def wait_for_run_engine_status(
    client: FlaskClient,
    status_check: Callable[[str], bool] = lambda status: status != Status.BUSY.value,
    attempts=10,
):
    while attempts != 0:
        response = client.get(STATUS_ENDPOINT)
        response_json = json.loads(response.data)
        LOGGER.debug(
            f"Checking client status - response: {response_json}, attempts left={attempts}"
        )
        if status_check(response_json["status"]):
            return response_json
        else:
            attempts -= 1
            sleep(0.2)
    raise AssertionError("Run engine still busy")


def check_status_in_response(response_object, expected_result: Status):
    response_json = json.loads(response_object.data)
    assert response_json["status"] == expected_result.value, (
        f"{response_json['status']} != {expected_result.value}: {response_json.get('message')}"
    )


@pytest.mark.timeout(5)
def test_start_gives_success(test_env: ClientAndRunEngine):
    response = test_env.client.put(START_ENDPOINT, data=TEST_PARAMS)
    check_status_in_response(response, Status.SUCCESS)


@pytest.mark.timeout(4)
def test_getting_status_return_idle(test_env: ClientAndRunEngine):
    test_env.client.put(START_ENDPOINT, data=TEST_PARAMS)
    test_env.client.put(STOP_ENDPOINT)
    response = test_env.client.get(STATUS_ENDPOINT)
    check_status_in_response(response, Status.IDLE)


@pytest.mark.timeout(5)
def test_getting_status_after_start_sent_returns_busy(
    test_env: ClientAndRunEngine,
):
    test_env.client.put(START_ENDPOINT, data=TEST_PARAMS)
    response = test_env.client.get(STATUS_ENDPOINT)
    check_status_in_response(response, Status.BUSY)


def test_putting_bad_plan_fails(test_env: ClientAndRunEngine):
    response = test_env.client.put("/bad_plan/start", data=TEST_PARAMS).json
    assert isinstance(response, dict)
    assert response.get("status") == Status.FAILED.value
    assert (
        response.get("message")
        == "PlanNotFound(\"Experiment plan 'bad_plan' not found in registry.\")"
    )
    test_env.mock_run_engine.abort()


def test_plan_with_no_params_fails(test_env: ClientAndRunEngine):
    response = test_env.client.put(
        "/test_experiment_no_internal_param_type/start", data=TEST_PARAMS
    ).json
    assert isinstance(response, dict)
    assert response.get("status") == Status.FAILED.value
    assert isinstance(message := response.get("message"), str)
    assert "'test_experiment_no_internal_param_type' not found in registry." in message
    test_env.mock_run_engine.abort()


@pytest.mark.timeout(7)
def test_sending_start_twice_fails(test_env: ClientAndRunEngine):
    test_env.client.put(START_ENDPOINT, data=TEST_PARAMS)
    response = test_env.client.put(START_ENDPOINT, data=TEST_PARAMS)
    check_status_in_response(response, Status.FAILED)


@pytest.mark.timeout(5)
def test_given_started_when_stopped_then_success_and_idle_status(
    test_env: ClientAndRunEngine,
):
    test_env.mock_run_engine.aborting_takes_time = True
    test_env.client.put(START_ENDPOINT, data=TEST_PARAMS)
    response = test_env.client.put(STOP_ENDPOINT)
    check_status_in_response(response, Status.ABORTING)
    response = test_env.client.get(STATUS_ENDPOINT)
    check_status_in_response(response, Status.ABORTING)
    test_env.mock_run_engine.aborting_takes_time = False
    wait_for_run_engine_status(
        test_env.client, lambda status: status != Status.ABORTING
    )
    check_status_in_response(response, Status.ABORTING)


@pytest.mark.timeout(10)
def test_given_started_when_stopped_and_started_again_then_runs(
    test_env: ClientAndRunEngine,
):
    test_env.client.put(START_ENDPOINT, data=TEST_PARAMS)
    test_env.client.put(STOP_ENDPOINT)
    test_env.mock_run_engine.RE_takes_time = True
    response = test_env.client.put(START_ENDPOINT, data=TEST_PARAMS)
    check_status_in_response(response, Status.SUCCESS)
    response = test_env.client.get(STATUS_ENDPOINT)
    check_status_in_response(response, Status.BUSY)
    test_env.mock_run_engine.RE_takes_time = False


@pytest.mark.timeout(5)
def test_when_started_n_returnstatus_interrupted_bc_RE_aborted_thn_error_reptd(
    test_env: ClientAndRunEngine,
):
    test_env.mock_run_engine.aborting_takes_time = True
    test_env.client.put(START_ENDPOINT, data=TEST_PARAMS)
    test_env.client.put(STOP_ENDPOINT)
    test_env.mock_run_engine.error = Exception("D'Oh")
    response_json = wait_for_run_engine_status(
        test_env.client, lambda status: status != Status.ABORTING.value
    )
    assert response_json["status"] == Status.FAILED.value
    assert response_json["message"] == 'Exception("D\'Oh")'
    assert response_json["exception_type"] == "Exception"


@pytest.mark.timeout(5)
@pytest.mark.parametrize(
    "endpoint, test_file",
    [
        [
            "/grid_detect_then_xray_centre/start",
            "tests/test_data/parameter_json_files/good_test_grid_with_edge_detect_parameters.json",
        ],
        [
            "/multi_rotation_scan/start",
            "tests/test_data/parameter_json_files/good_test_one_multi_rotation_scan_parameters.json",
        ],
        [
            "/pin_tip_centre_then_xray_centre/start",
            "tests/test_data/parameter_json_files/good_test_pin_centre_then_xray_centre_parameters.json",
        ],
        [
            "/multi_rotation_scan/start",
            "tests/test_data/parameter_json_files/good_test_multi_rotation_scan_parameters.json",
        ],
        [
            "/load_centre_collect_full/start",
            "tests/test_data/parameter_json_files/good_test_load_centre_collect_params.json",
        ],
    ],
)
def test_start_with_json_file_gives_success(
    test_env: ClientAndRunEngine, endpoint: str, test_file: str
):
    test_env.mock_run_engine.RE_takes_time = False

    with open(test_file) as test_params_file:
        test_params = test_params_file.read()
    response = test_env.client.put(endpoint, data=test_params)
    check_status_in_response(response, Status.SUCCESS)


@pytest.mark.timeout(3)
def test_start_with_json_file_with_extras_gives_error(test_env: ClientAndRunEngine):
    test_env.mock_run_engine.RE_takes_time = False

    with open(
        "tests/test_data/parameter_json_files/good_test_parameters.json"
    ) as test_params_file:
        test_params = test_params_file.read()

    params = json.loads(test_params)
    params["extra_param"] = "test"
    test_params = json.dumps(params)
    response = test_env.client.put(START_ENDPOINT, data=test_params)
    check_status_in_response(response, Status.FAILED)


@pytest.mark.parametrize(
    ["arg_list", "parsed_arg_values"],
    [
        (
            [
                "--dev",
            ],
            (True, False),
        ),
        ([], (False, False)),
        (
            [
                "--dev",
                "--verbose-event-logging",
            ],
            (True, True),
        ),
    ],
)
def test_cli_args_parse(arg_list, parsed_arg_values):
    argv[1:] = arg_list
    test_args = parse_cli_args()
    assert test_args.dev_mode == parsed_arg_values[0]
    assert test_args.verbose_event_logging == parsed_arg_values[1]


@pytest.mark.skip(
    "Wait for connection doesn't play nice with ophyd-async. See https://github.com/DiamondLightSource/hyperion/issues/1159"
)
def test_when_blueskyrunner_initiated_then_plans_are_setup_and_devices_connected():
    zebra = MagicMock(spec=Zebra)
    attenuator = MagicMock(spec=BinaryFilterAttenuator)

    context = BlueskyContext()
    context.register_device(zebra, "zebra")
    context.register_device(attenuator, "attenuator")

    @dataclass
    class FakeComposite:
        attenuator: BinaryFilterAttenuator
        zebra: Zebra

    # A fake setup for a plan that uses two devices: attenuator and zebra.
    def fake_create_devices(context) -> FakeComposite:
        print("CREATING DEVICES")
        return device_composite_from_context(context, FakeComposite)

    with patch.dict(
        "mx_bluesky.hyperion.__main__.PLAN_REGISTRY",
        {
            "flyscan_xray_centre": {
                "setup": fake_create_devices,
                "param_type": MagicMock(),
            },
        },
        clear=True,
    ):
        print(PLAN_REGISTRY)

        BlueskyRunner(
            RE=MagicMock(),
            context=context,
        )

    zebra.wait_for_connection.assert_called()
    attenuator.wait_for_connection.assert_called()


@patch(
    "mx_bluesky.hyperion.experiment_plans.rotation_scan_plan.create_devices",
    autospec=True,
)
def test_when_blueskyrunner_initiated_then_setup_called_upon_start(
    mock_setup, hyperion_fgs_params: HyperionSpecifiedThreeDGridScan
):
    mock_setup = MagicMock()
    with patch.dict(
        "mx_bluesky.hyperion.__main__.PLAN_REGISTRY",
        {
            "multi_rotation_scan": {
                "setup": mock_setup,
                "param_type": MagicMock(),
            },
        },
        clear=True,
    ):
        runner = BlueskyRunner(MagicMock(), MagicMock())
        mock_setup.assert_not_called()
        runner.start(lambda: None, hyperion_fgs_params, "multi_rotation_scan")
        mock_setup.assert_called_once()
        runner.shutdown()


def test_log_on_invalid_json_params(test_env: ClientAndRunEngine):
    test_env.mock_run_engine.RE_takes_time = False
    response = test_env.client.put(TEST_BAD_PARAM_ENDPOINT, data='{"bad":1}').json
    assert isinstance(response, dict)
    assert response.get("status") == Status.FAILED.value
    assert (message := response.get("message")) is not None
    assert message.startswith(
        "ValueError('Supplied parameters don\\'t match the plan for this endpoint"
    )
    assert response.get("exception_type") == "ValueError"


@pytest.mark.skip(
    reason="See https://github.com/DiamondLightSource/hyperion/issues/777"
)
def test_warn_exception_during_plan_causes_warning_in_log(
    caplog: pytest.LogCaptureFixture, test_env: ClientAndRunEngine
):
    test_env.client.put(START_ENDPOINT, data=TEST_PARAMS)
    test_env.mock_run_engine.error = WarningException("D'Oh")
    response_json = wait_for_run_engine_status(test_env.client)
    assert response_json["status"] == Status.FAILED.value
    assert response_json["message"] == 'WarningException("D\'Oh")'
    assert response_json["exception_type"] == "WarningException"
    assert caplog.records[-1].levelname == "WARNING"


@patch(
    "dodal.devices.i03.undulator_dcm.get_beamline_parameters",
    return_value={"DCM_Perp_Offset_FIXED": 111},
)
def test_when_context_created_then_contains_expected_number_of_plans(
    get_beamline_parameters,
):
    from dodal.beamlines import i03

    mock_beamline_module_filepaths("i03", i03)

    with patch.dict(
        os.environ,
        {"BEAMLINE": "i03"},
    ):
        with patch(
            "mx_bluesky.hyperion.utils.context.BlueskyContext.with_dodal_module"
        ):
            context = setup_context()
        plan_names = context.plans.keys()

        # assert "rotation_scan" in plan_names
        # May want to add back in if we change name of multi_rotation_scan to rotation_scan
        assert "multi_rotation_scan" in plan_names
        assert "grid_detect_then_xray_centre" in plan_names
        assert "pin_tip_centre_then_xray_centre" in plan_names
