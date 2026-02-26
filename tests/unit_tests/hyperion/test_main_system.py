from __future__ import annotations

import os
import signal
import threading
from pathlib import Path
from sys import argv
from time import sleep
from unittest.mock import ANY, MagicMock, call, patch

import pytest
from blueapi.config import ApplicationConfig
from dodal.devices.baton import Baton
from ophyd_async.core import set_mock_value

from mx_bluesky.common.external_interaction.alerting.log_based_service import (
    LoggingAlertService,
)
from mx_bluesky.common.utils.context import (
    find_device_in_context,
)
from mx_bluesky.hyperion.__main__ import (
    initialise_globals,
    main,
)
from mx_bluesky.hyperion.baton_handler import HYPERION_USER
from mx_bluesky.hyperion.parameters.cli import (
    HyperionArgs,
    HyperionMode,
    parse_cli_args,
)
from mx_bluesky.hyperion.parameters.constants import CONST, HyperionConstants
from mx_bluesky.hyperion.plan_runner import PlanRunner

from .conftest import AGAMEMNON_WAIT_INSTRUCTION


@pytest.fixture(autouse=True)
def patch_remote_graylog_endpoint():
    with patch("dodal.log.get_graylog_configuration", return_value=("localhost", 5555)):
        yield None


@pytest.fixture(autouse=True)
def mock_create_udc_server():
    with patch("mx_bluesky.hyperion.__main__.create_server_for_udc") as mock_udc_server:
        yield mock_udc_server


@pytest.fixture
def mock_setup_context(request: pytest.FixtureRequest):
    with (
        patch("mx_bluesky.hyperion.__main__.setup_context") as mock_setup_context,
        patch("mx_bluesky.hyperion.__main__.run_forever"),
    ):
        yield mock_setup_context


@pytest.mark.parametrize(
    ["arg_list", "parsed_arg_values"],
    [
        (
            [
                "--dev",
            ],
            (True,),
        ),
        ([], (False,)),
    ],
)
def test_cli_args_parse(arg_list, parsed_arg_values):
    argv[1:] = arg_list
    test_args = parse_cli_args()
    assert test_args.dev_mode == parsed_arg_values[0]


@pytest.fixture(autouse=True)
def beamline_i03():
    with (
        patch.dict(os.environ, {"BEAMLINE": "i03"}),
        patch.dict(
            "dodal.common.beamlines.beamline_parameters.BEAMLINE_PARAMETER_PATHS",
            {"i03": "tests/test_data/test_beamline_parameters.txt"},
        ),
    ):
        yield


@patch("mx_bluesky.hyperion.__main__.do_default_logging_setup", MagicMock())
@pytest.mark.parametrize("dev_mode", [False, True])
def test_context_created_with_dev_mode(dev_mode: bool, mock_setup_context: MagicMock):
    with (
        patch("sys.argv", new=["hyperion", "--dev"] if dev_mode else ["hyperion"]),
        patch("mx_bluesky.hyperion.__main__.create_server_for_udc"),
    ):
        main()

    mock_setup_context.assert_called_once_with(dev_mode=dev_mode)


@patch("mx_bluesky.hyperion.__main__.do_default_logging_setup")
@patch("mx_bluesky.hyperion.__main__.alerting.set_alerting_service")
def test_initialise_configures_logging(
    mock_alerting_setup: MagicMock, mock_logging_setup: MagicMock
):
    args = HyperionArgs(mode=HyperionMode.UDC, dev_mode=True)

    initialise_globals(args)

    mock_logging_setup.assert_called_once_with(
        CONST.LOG_FILE_NAME, CONST.GRAYLOG_PORT, dev_mode=True
    )


@patch("mx_bluesky.hyperion.__main__.do_default_logging_setup")
@patch("mx_bluesky.hyperion.__main__.alerting.set_alerting_service")
def test_initialise_configures_alerting(
    mock_alerting_setup: MagicMock, mock_logging_setup: MagicMock
):
    args = HyperionArgs(mode=HyperionMode.UDC, dev_mode=True)

    initialise_globals(args)

    mock_alerting_setup.assert_called_once()
    assert isinstance(mock_alerting_setup.mock_calls[0].args[0], LoggingAlertService)


@patch("sys.argv", new=["hyperion", "--mode", "udc"])
@patch("mx_bluesky.hyperion.__main__.do_default_logging_setup")
@patch("mx_bluesky.hyperion.__main__.create_server_for_udc", MagicMock())
@patch("mx_bluesky.hyperion.__main__.run_forever", MagicMock())
def test_hyperion_in_udc_mode_starts_logging(
    mock_do_default_logging_setup: MagicMock,
    mock_setup_context: MagicMock,
):
    main()

    mock_do_default_logging_setup.assert_called_once_with(
        CONST.LOG_FILE_NAME, CONST.GRAYLOG_PORT, dev_mode=False
    )


@patch("sys.argv", new=["hyperion", "--mode", "udc"])
@patch("mx_bluesky.hyperion.__main__.do_default_logging_setup", MagicMock())
@patch("mx_bluesky.hyperion.__main__.run_forever", MagicMock())
def test_hyperion_in_udc_mode_starts_udc_api(
    mock_create_udc_server: MagicMock,
    mock_setup_context: MagicMock,
):
    main()
    mock_create_udc_server.assert_called_once()
    assert isinstance(mock_create_udc_server.mock_calls[0].args[0], PlanRunner)


@patch("sys.argv", new=["hyperion", "--mode", "udc"])
@patch("mx_bluesky.hyperion.__main__.setup_context")
@patch("mx_bluesky.hyperion.__main__.run_forever")
@patch("mx_bluesky.hyperion.baton_handler.find_device_in_context", autospec=True)
@patch("mx_bluesky.hyperion.__main__.do_default_logging_setup", MagicMock())
def test_hyperion_in_udc_mode_starts_udc_loop(
    mock_find_device_in_context: MagicMock,
    mock_run_forever: MagicMock,
    mock_setup_context: MagicMock,
):
    main()

    mock_run_forever.assert_called_once()
    assert isinstance(mock_run_forever.mock_calls[0].args[0], PlanRunner)


@patch(
    "sys.argv",
    new=["hyperion", "--mode", "supervisor", "--supervisor-config", "test_config"],
)
@patch("mx_bluesky.hyperion.__main__.do_default_logging_setup", MagicMock())
def test_hyperion_in_supervisor_mode_requires_client_config_option():
    with pytest.raises(
        RuntimeError,
        match="BlueAPI client configuration file must be specified in supervisor mode.",
    ):
        main()


@patch(
    "sys.argv",
    new=["hyperion", "--mode", "supervisor", "--client-config", "test_config"],
)
@patch("mx_bluesky.hyperion.__main__.do_default_logging_setup", MagicMock())
def test_hyperion_in_supervisor_mode_requires_supervisor_config_option():
    with pytest.raises(
        RuntimeError,
        match="BlueAPI supervisor configuration file must be specified in supervisor mode.",
    ):
        main()


@pytest.fixture
def mock_supervisor_mode():
    parent = MagicMock()
    with patch.multiple(
        "mx_bluesky.hyperion.__main__",
        ConfigLoader=parent.ConfigLoader,
        BlueskyContext=parent.BlueskyContext,
        run_forever=parent.run_forever,
        signal=parent.signal,
        SupervisorRunner=parent.SupervisorRunner,
    ):
        yield parent


@patch(
    "sys.argv",
    new=[
        "hyperion",
        "--mode",
        "supervisor",
        "--client-config",
        "test_client_config",
        "--supervisor-config",
        "test_supervisor_config",
    ],
)
@patch("mx_bluesky.hyperion.__main__.run_forever", MagicMock())
@patch("mx_bluesky.hyperion.__main__.do_default_logging_setup", MagicMock())
def test_hyperion_in_supervisor_mode_creates_rest_server_on_supervisor_port(
    mock_supervisor_mode: MagicMock,
    mock_create_udc_server: MagicMock,
):
    mock_supervisor_mode.ConfigLoader.return_value.load.side_effect = [
        "client_config",
        "supervisor_config",
    ]
    main()
    mock_supervisor_mode.assert_has_calls(
        [
            call.ConfigLoader(ApplicationConfig),
            call.ConfigLoader().use_values_from_yaml(Path("test_client_config")),
            call.ConfigLoader().load(),
            call.ConfigLoader(ApplicationConfig),
            call.ConfigLoader().use_values_from_yaml(Path("test_supervisor_config")),
            call.ConfigLoader().load(),
            call.BlueskyContext(configuration="supervisor_config"),
            call.SupervisorRunner(ANY, "client_config", False),
        ]
    )
    mock_create_udc_server.assert_called_once_with(
        ANY, HyperionConstants.SUPERVISOR_PORT
    )


@patch("sys.argv", new=["hyperion", "--mode", "udc", "--dev"])
@patch(
    "mx_bluesky.hyperion.baton_handler.create_parameters_from_agamemnon",
    return_value=[AGAMEMNON_WAIT_INSTRUCTION],
)
@patch("mx_bluesky.hyperion.baton_handler.clear_all_device_caches", MagicMock())
@patch("mx_bluesky.hyperion.baton_handler.setup_devices", MagicMock())
def test_sending_main_process_sigterm_in_udc_mode_performs_clean_prompt_shutdown(
    mock_create_parameters_from_agamemnon,
    use_beamline_t01,
    mock_create_udc_server,
):
    def wait_for_udc_to_start_then_send_sigterm():
        while len(mock_create_udc_server.mock_calls) == 0:
            sleep(0.2)

        plan_runner = mock_create_udc_server.mock_calls[0].args[0]
        context = plan_runner.context
        baton = find_device_in_context(context, "baton", Baton)
        set_mock_value(baton.requested_user, HYPERION_USER)
        while len(mock_create_parameters_from_agamemnon.mock_calls) == 0:
            sleep(0.2)
        os.kill(os.getpid(), signal.SIGTERM)

    t = threading.Thread(None, wait_for_udc_to_start_then_send_sigterm, daemon=True)
    t.start()
    main()
