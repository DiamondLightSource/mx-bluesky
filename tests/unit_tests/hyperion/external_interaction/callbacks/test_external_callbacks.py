from __future__ import annotations

from functools import partial
from threading import Event
from time import sleep
from unittest.mock import MagicMock, patch

import pytest
from dodal.log import LOGGER as DODAL_LOGGER

from mx_bluesky.common.external_interaction.alerting.log_based_service import (
    LoggingAlertService,
)
from mx_bluesky.common.utils.log import ISPYB_ZOCALO_CALLBACK_LOGGER, NEXUS_LOGGER
from mx_bluesky.hyperion.external_interaction.callbacks.__main__ import (
    PING_TIMEOUT_S,
    main,
    run_watchdog,
    setup_callbacks,
    setup_logging,
    wait_for_threads_forever,
)


@patch("mx_bluesky.hyperion.external_interaction.callbacks.__main__.run_watchdog")
@patch(
    "mx_bluesky.hyperion.external_interaction.callbacks.__main__.parse_callback_dev_mode_arg",
    return_value=("DEBUG", True),
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
    parse_callback_dev_mode_arg: MagicMock,
    mock_run_watchdog: MagicMock,
):
    proxy_started = Event()
    dispatcher_started = Event()
    watchdog_started = Event()
    mock_proxy.return_value.start.side_effect = proxy_started.set
    mock_dispatcher.return_value.start.side_effect = dispatcher_started.set
    mock_run_watchdog.side_effect = watchdog_started.set

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
    "mx_bluesky.hyperion.external_interaction.callbacks.__main__.parse_callback_dev_mode_arg",
    return_value=True,
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

    mock_threads = [thread_that_stops_after_one_call, MagicMock()]

    wait_for_threads_forever(mock_threads)
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
        run_watchdog()

    mock_request.urlopen.assert_called_with(
        "http://localhost:5005/callbackPing", timeout=PING_TIMEOUT_S
    )
