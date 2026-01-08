from __future__ import annotations

from functools import partial
from threading import Event
from time import sleep
from unittest.mock import MagicMock, Mock, call, patch

import pytest
from bluesky.callbacks import CallbackBase
from bluesky_stomp.models import Broker
from dodal.log import LOGGER as DODAL_LOGGER

from mx_bluesky.common.external_interaction.alerting.log_based_service import (
    LoggingAlertService,
)
from mx_bluesky.common.utils.log import ISPYB_ZOCALO_CALLBACK_LOGGER, NEXUS_LOGGER
from mx_bluesky.hyperion.external_interaction.callbacks.__main__ import (
    PING_TIMEOUT_S,
    main,
    ping_watchdog_while_alive,
    run_watchdog,
    setup_callbacks,
    setup_logging,
)
from mx_bluesky.hyperion.parameters.cli import CallbackArgs
from mx_bluesky.hyperion.parameters.constants import HyperionConstants


@patch("mx_bluesky.hyperion.external_interaction.callbacks.__main__.run_watchdog")
@patch(
    "mx_bluesky.hyperion.external_interaction.callbacks.__main__.parse_callback_args",
    return_value=CallbackArgs(True, HyperionConstants.SUPERVISOR_PORT),
)
@patch("mx_bluesky.hyperion.external_interaction.callbacks.__main__.setup_callbacks")
@patch("mx_bluesky.hyperion.external_interaction.callbacks.__main__.setup_logging")
@patch(
    "mx_bluesky.hyperion.external_interaction.callbacks.__main__.set_alerting_service"
)
@patch("mx_bluesky.hyperion.external_interaction.callbacks.__main__.RemoteDispatcher")
@patch("mx_bluesky.hyperion.external_interaction.callbacks.__main__.Proxy")
def test_main_function(
    mock_proxy: MagicMock,
    mock_dispatcher: MagicMock,
    setup_alerting: MagicMock,
    setup_logging: MagicMock,
    setup_callbacks: MagicMock,
    parse_callback_args: MagicMock,
    mock_run_watchdog: MagicMock,
):
    proxy_started = Event()
    dispatcher_started = Event()
    watchdog_started = Event()
    mock_proxy.return_value.start.side_effect = proxy_started.set
    mock_dispatcher.return_value.start.side_effect = dispatcher_started.set
    mock_run_watchdog.side_effect = lambda _: watchdog_started.set() or None

    main()

    proxy_started.wait(0.5)
    dispatcher_started.wait(0.5)
    mock_run_watchdog.wait(0.5)
    setup_logging.assert_called()
    setup_callbacks.assert_called()
    setup_alerting.assert_called_once()
    mock_run_watchdog.assert_called_once()
    assert isinstance(setup_alerting.mock_calls[0].args[0], LoggingAlertService)


def test_setup_callbacks():
    current_number_of_callbacks = 8
    cbs = setup_callbacks()
    assert len(cbs) == current_number_of_callbacks
    assert len(set(cbs)) == current_number_of_callbacks


@pytest.mark.skip_log_setup
@patch(
    "mx_bluesky.hyperion.external_interaction.callbacks.__main__.parse_callback_args",
    return_value=CallbackArgs(True, HyperionConstants.SUPERVISOR_PORT),
)
def test_setup_logging(parse_callback_cli_args):
    assert DODAL_LOGGER.parent != ISPYB_ZOCALO_CALLBACK_LOGGER
    assert len(ISPYB_ZOCALO_CALLBACK_LOGGER.handlers) == 0
    assert len(NEXUS_LOGGER.handlers) == 0
    setup_logging(parse_callback_cli_args())
    assert len(ISPYB_ZOCALO_CALLBACK_LOGGER.handlers) == 4
    assert len(NEXUS_LOGGER.handlers) == 4
    assert DODAL_LOGGER.parent == ISPYB_ZOCALO_CALLBACK_LOGGER
    setup_logging(parse_callback_cli_args())
    assert len(ISPYB_ZOCALO_CALLBACK_LOGGER.handlers) == 4
    assert len(NEXUS_LOGGER.handlers) == 4


@patch("mx_bluesky.hyperion.external_interaction.callbacks.__main__.sleep")
def test_wait_for_threads_forever_calls_time_sleep(mock_sleep: MagicMock):
    thread_that_stops_after_one_call = MagicMock()
    thread_that_stops_after_one_call.is_alive.side_effect = [True, False]

    mock_context_manager = MagicMock()
    mock_context_manager.is_alive.side_effect = [True, False]

    ping_watchdog_while_alive(thread_that_stops_after_one_call, mock_context_manager)
    assert mock_sleep.call_count == 1


@patch("mx_bluesky.hyperion.external_interaction.callbacks.__main__.RemoteDispatcher")
@patch("mx_bluesky.hyperion.external_interaction.callbacks.__main__.Proxy")
@patch("mx_bluesky.hyperion.external_interaction.callbacks.__main__.request")
@patch(
    "mx_bluesky.hyperion.external_interaction.callbacks.__main__.LIVENESS_POLL_SECONDS",
    0.1,
)
def test_launching_external_callbacks_pings_regularly(
    mock_request: MagicMock,
    mock_proxy: MagicMock,
    mock_dispatcher: MagicMock,
):
    mock_proxy.return_value.start.side_effect = partial(sleep, 0.1)
    mock_dispatcher.return_value.start.side_effect = partial(sleep, 0.1)
    mock_request.urlopen.return_value.__enter__.return_value.status = 200
    mock_request.urlopen.return_value.__exit__.side_effect = RuntimeError(
        "Exit this thread"
    )

    with pytest.raises(RuntimeError, match="Exit this thread"):
        run_watchdog(5005)

    mock_request.urlopen.assert_called_with(
        "http://localhost:5005/callbackPing", timeout=PING_TIMEOUT_S
    )


@patch("sys.argv", new=["hyperion-callbacks", "--watchdog-port", "1234"])
@patch(
    "mx_bluesky.hyperion.external_interaction.callbacks.__main__.HyperionCallbackRunner"
)
def test_launch_with_watchdog_port_arg_applies_port(mock_callback_runner: MagicMock):
    main(dev_mode=True)
    mock_callback_runner.assert_called_once()
    callback_args = mock_callback_runner.mock_calls[0].args[0]
    assert callback_args.dev_mode
    assert callback_args.watchdog_port == 1234


@patch(
    "sys.argv",
    new=[
        "hyperion-callbacks",
        "--watchdog-port",
        "1234",
        "--stomp-config",
        "tests/test_data/stomp_callback_test_config.yaml",
    ],
)
@patch("mx_bluesky.hyperion.external_interaction.callbacks.__main__.StompDispatcher")
@patch("mx_bluesky.hyperion.external_interaction.callbacks.__main__.StompClient")
@patch(
    "mx_bluesky.hyperion.external_interaction.callbacks.__main__.setup_callbacks",
    return_value=[Mock(spec=CallbackBase)],
)
@patch(
    "mx_bluesky.hyperion.external_interaction.callbacks.__main__.LIVENESS_POLL_SECONDS",
    0.1,
)
def test_launch_with_stomp_launches_stomp_backend(
    mock_setup_callbacks: MagicMock,
    mock_client_cls: MagicMock,
    mock_dispatcher_cls: MagicMock,
):
    stomp_client = mock_client_cls.for_broker.return_value
    dispatcher = mock_dispatcher_cls.return_value
    stomp_client.is_connected.side_effect = [True, False]

    parent = MagicMock()
    parent.attach_mock(stomp_client, "stomp_client")
    parent.attach_mock(dispatcher, "dispatcher")
    main(dev_mode=True)

    mock_client_cls.for_broker.assert_called_once_with(
        broker=Broker(host="localhost", port=61613, auth=None)
    )
    mock_dispatcher_cls.assert_called_once_with(stomp_client)
    parent.assert_has_calls(
        [
            call.dispatcher.subscribe(mock_setup_callbacks.return_value[0]),
            call.dispatcher.__enter__(),
            call.stomp_client.is_connected(),
            call.stomp_client.is_connected(),
            call.dispatcher.__exit__(None, None, None),
        ]
    )
