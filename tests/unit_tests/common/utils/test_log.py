import os
from logging import FileHandler
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp
from dodal.log import LOGGER as dodal_logger
from dodal.log import set_up_all_logging_handlers

import mx_bluesky.common.utils.log as log
import mx_bluesky.hyperion.log as hyperion_log
from mx_bluesky.hyperion.external_interaction.callbacks.log_uid_tag_callback import (
    LogUidTaggingCallback,
)

from ....conftest import clear_log_handlers

TEST_GRAYLOG_PORT = 5555


@pytest.fixture(scope="function")
def clear_and_mock_loggers():
    clear_log_handlers([*hyperion_log.ALL_LOGGERS, dodal_logger])
    mock_open_with_tell = MagicMock()
    mock_open_with_tell.tell.return_value = 0
    with (
        patch("dodal.log.logging.FileHandler._open", mock_open_with_tell),
        patch("dodal.log.GELFTCPHandler.emit") as graylog_emit,
        patch("dodal.log.TimedRotatingFileHandler.emit") as filehandler_emit,
    ):
        graylog_emit.reset_mock()
        filehandler_emit.reset_mock()
        yield filehandler_emit, graylog_emit
    clear_log_handlers([*hyperion_log.ALL_LOGGERS, dodal_logger])


@pytest.mark.skip_log_setup
def test_no_env_variable_sets_correct_file_handler(
    clear_and_mock_loggers,
) -> None:
    log.do_default_logging_setup("hyperion.log", TEST_GRAYLOG_PORT, dev_mode=True)
    file_handlers: FileHandler = next(
        filter(lambda h: isinstance(h, FileHandler), dodal_logger.handlers)  # type: ignore
    )

    assert file_handlers.baseFilename.endswith("/tmp/logs/bluesky/hyperion.log")


@pytest.mark.skip_log_setup
@patch("dodal.log.Path.mkdir", autospec=True)
@patch.dict(
    os.environ, {"LOG_DIR": "./dls_sw/s03/logs/bluesky"}
)  # Note we use a relative path here so it works in CI
def test_set_env_variable_sets_correct_file_handler(
    mock_dir,
    clear_and_mock_loggers,
) -> None:
    log.do_default_logging_setup("hyperion.log", TEST_GRAYLOG_PORT, dev_mode=True)

    file_handlers: FileHandler = next(
        filter(lambda h: isinstance(h, FileHandler), dodal_logger.handlers)  # type: ignore
    )

    assert file_handlers.baseFilename.endswith("/dls_sw/s03/logs/bluesky/hyperion.log")


@pytest.mark.skip_log_setup
def test_messages_logged_from_dodal_and_hyperion_contain_dcgid(
    clear_and_mock_loggers,
):
    _, mock_GELFTCPHandler_emit = clear_and_mock_loggers
    log.do_default_logging_setup("hyperion.log", TEST_GRAYLOG_PORT, dev_mode=True)

    log.set_dcgid_tag(100)

    logger = hyperion_log.LOGGER
    logger.info("test_hyperion")
    dodal_logger.info("test_dodal")

    graylog_calls = mock_GELFTCPHandler_emit.mock_calls[1:]

    dc_group_id_correct = [c.args[0].dc_group_id == 100 for c in graylog_calls]
    assert all(dc_group_id_correct)


@pytest.mark.skip_log_setup
def test_messages_are_tagged_with_run_uid(clear_and_mock_loggers, RE):
    _, mock_GELFTCPHandler_emit = clear_and_mock_loggers
    log.do_default_logging_setup("hyperion.log", TEST_GRAYLOG_PORT, dev_mode=True)

    RE.subscribe(LogUidTaggingCallback())
    test_run_uid = None
    logger = hyperion_log.LOGGER

    @bpp.run_decorator()
    def test_plan():
        yield from bps.sleep(0)
        assert log.tag_filter.run_uid is not None
        nonlocal test_run_uid
        test_run_uid = log.tag_filter.run_uid
        logger.info("test_hyperion")
        logger.info("test_hyperion")
        yield from bps.sleep(0)

    assert log.tag_filter.run_uid is None
    RE(test_plan())
    assert log.tag_filter.run_uid is None

    graylog_calls_in_plan = [
        c.args[0]
        for c in mock_GELFTCPHandler_emit.mock_calls
        if c.args[0].msg == "test_hyperion"
    ]

    assert len(graylog_calls_in_plan) == 2

    dc_group_id_correct = [
        record.run_uid == test_run_uid for record in graylog_calls_in_plan
    ]
    assert all(dc_group_id_correct)


@pytest.mark.skip_log_setup
def test_messages_logged_from_dodal_and_hyperion_get_sent_to_graylog_and_file(
    clear_and_mock_loggers,
):
    mock_filehandler_emit, mock_GELFTCPHandler_emit = clear_and_mock_loggers
    log.do_default_logging_setup("hyperion.log", TEST_GRAYLOG_PORT, dev_mode=True)
    logger = hyperion_log.LOGGER
    logger.info("test_hyperion")
    dodal_logger.info("test_dodal")

    filehandler_calls = mock_filehandler_emit.mock_calls
    graylog_calls = mock_GELFTCPHandler_emit.mock_calls

    assert len(filehandler_calls) >= 2
    assert len(graylog_calls) >= 2

    for handler in [filehandler_calls, graylog_calls]:
        handler_names = [c.args[0].name for c in handler]
        handler_messages = [c.args[0].message for c in handler]
        assert "Hyperion" in handler_names
        assert "Dodal" in handler_names
        assert "test_hyperion" in handler_messages
        assert "test_dodal" in handler_messages


@pytest.mark.skip_log_setup
def test_callback_loggers_log_to_own_files(
    clear_and_mock_loggers,
):
    mock_filehandler_emit, mock_GELFTCPHandler_emit = clear_and_mock_loggers
    log.do_default_logging_setup("hyperion.log", TEST_GRAYLOG_PORT, dev_mode=True)

    hyperion_logger = hyperion_log.LOGGER
    ispyb_logger = hyperion_log.ISPYB_LOGGER
    nexus_logger = hyperion_log.NEXUS_LOGGER
    for logger in [ispyb_logger, nexus_logger]:
        set_up_all_logging_handlers(
            logger, log._get_logging_dir(), logger.name, True, 10000
        )

    hyperion_logger.info("test_hyperion")
    ispyb_logger.info("test_ispyb")
    nexus_logger.info("test_nexus")

    total_filehandler_calls = mock_filehandler_emit.mock_calls
    total_graylog_calls = mock_GELFTCPHandler_emit.mock_calls

    assert len(total_filehandler_calls) == len(total_graylog_calls)

    hyperion_filehandler = next(
        filter(lambda h: isinstance(h, TimedRotatingFileHandler), dodal_logger.handlers)  # type: ignore
    )
    ispyb_filehandler = next(
        filter(lambda h: isinstance(h, TimedRotatingFileHandler), ispyb_logger.handlers)  # type: ignore
    )
    nexus_filehandler = next(
        filter(lambda h: isinstance(h, TimedRotatingFileHandler), nexus_logger.handlers)  # type: ignore
    )
    assert nexus_filehandler.baseFilename != hyperion_filehandler.baseFilename  # type: ignore
    assert ispyb_filehandler.baseFilename != hyperion_filehandler.baseFilename  # type: ignore
    assert ispyb_filehandler.baseFilename != nexus_filehandler.baseFilename  # type: ignore


@pytest.mark.skip_log_setup
def test_log_writes_debug_file_on_error(clear_and_mock_loggers):
    mock_filehandler_emit, _ = clear_and_mock_loggers
    log.do_default_logging_setup("hyperion.log", TEST_GRAYLOG_PORT, dev_mode=True)
    hyperion_log.LOGGER.debug("debug_message_1")
    hyperion_log.LOGGER.debug("debug_message_2")
    mock_filehandler_emit.assert_not_called()
    hyperion_log.LOGGER.error("error happens")
    assert len(mock_filehandler_emit.mock_calls) == 4
    messages = [call.args[0].message for call in mock_filehandler_emit.mock_calls]
    assert "debug_message_1" in messages
    assert "debug_message_2" in messages
    assert "error happens" in messages


@patch("mx_bluesky.common.utils.log.Path.mkdir")
def test_get_logging_dir_uses_env_var(mock_mkdir: MagicMock):
    def mock_get_log_dir(variable: str):
        if variable == "LOG_DIR":
            return "test_dir"
        else:
            return "other_dir"

    with patch(
        "mx_bluesky.common.utils.log.environ.get",
        side_effect=lambda var: mock_get_log_dir(var),
    ):
        assert log._get_logging_dir() == Path("test_dir")
        mock_mkdir.assert_called_once()


@patch("mx_bluesky.common.utils.log.Path.mkdir")
def test_get_logging_dir_uses_beamline_if_no_dir_env_var(mock_mkdir: MagicMock):
    def mock_get_log_dir(variable: str):
        if variable == "LOG_DIR":
            return None
        elif variable == "BEAMLINE":
            return "test"

    with patch(
        "mx_bluesky.common.utils.log.environ.get",
        side_effect=lambda var: mock_get_log_dir(var),
    ):
        assert log._get_logging_dir() == Path("/dls_sw/test/logs/bluesky/")
        mock_mkdir.assert_called_once()


@patch("mx_bluesky.common.utils.log.Path.mkdir")
def test_get_logging_dir_uses_tmp_if_no_env_var(mock_mkdir: MagicMock):
    assert log._get_logging_dir() == Path("/tmp/logs/bluesky")
    mock_mkdir.assert_called_once()


@pytest.mark.skip_log_setup
@patch("mx_bluesky.common.utils.log.Path.mkdir")
@patch(
    "mx_bluesky.common.utils.log.integrate_bluesky_and_ophyd_logging",
)
def test_default_logging_setup_integrate_logs_flag(
    mock_integrate_logs: MagicMock, mock_mkdir
):
    log.do_default_logging_setup(
        "hyperion.log", TEST_GRAYLOG_PORT, dev_mode=True, integrate_all_logs=False
    )
    mock_integrate_logs.assert_not_called()