import os
from logging import FileHandler
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp
from dodal.log import LOGGER as DODAL_LOGGER
from dodal.log import set_up_all_logging_handlers

import mx_bluesky.common.utils.log as log
from mx_bluesky.common.external_interaction.callbacks.common.log_uid_tag_callback import (
    LogUidTaggingCallback,
)

from ....conftest import clear_log_handlers

TEST_GRAYLOG_PORT = 5555


@pytest.fixture(scope="function")
def clear_and_mock_loggers():
    clear_log_handlers([*log.ALL_LOGGERS, DODAL_LOGGER])
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
    clear_log_handlers([*log.ALL_LOGGERS, DODAL_LOGGER])


@pytest.mark.skip_log_setup
def test_no_env_variable_sets_correct_file_handler(
    clear_and_mock_loggers,
) -> None:
    log.do_default_logging_setup("hyperion.log", TEST_GRAYLOG_PORT, dev_mode=True)
    file_handlers: FileHandler = next(
        filter(lambda h: isinstance(h, FileHandler), DODAL_LOGGER.handlers)  # type: ignore
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
        filter(lambda h: isinstance(h, FileHandler), DODAL_LOGGER.handlers)  # type: ignore
    )

    assert file_handlers.baseFilename.endswith("/dls_sw/s03/logs/bluesky/hyperion.log")


@pytest.mark.skip_log_setup
def test_messages_logged_from_dodal_and_hyperion_contain_dcgid(
    clear_and_mock_loggers,
):
    _, mock_gelf_tcp_handler_emit = clear_and_mock_loggers
    log.do_default_logging_setup("hyperion.log", TEST_GRAYLOG_PORT, dev_mode=True)

    log.set_dcgid_tag(100)

    logger = log.LOGGER
    logger.info("test_hyperion")
    DODAL_LOGGER.info("test_dodal")

    graylog_calls = mock_gelf_tcp_handler_emit.mock_calls[1:]

    dc_group_id_correct = [c.args[0].dc_group_id == 100 for c in graylog_calls]
    assert all(dc_group_id_correct)


@pytest.mark.skip_log_setup
def test_messages_are_tagged_with_run_uid(clear_and_mock_loggers, run_engine):
    _, mock_gelf_tcp_handler_emit = clear_and_mock_loggers
    log.do_default_logging_setup("hyperion.log", TEST_GRAYLOG_PORT, dev_mode=True)

    run_engine.subscribe(LogUidTaggingCallback())
    test_run_uid = None
    logger = log.LOGGER

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
    run_engine(test_plan())
    assert log.tag_filter.run_uid is None

    graylog_calls_in_plan = [
        c.args[0]
        for c in mock_gelf_tcp_handler_emit.mock_calls
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
    mock_filehandler_emit, mock_gelf_tcp_handler_emit = clear_and_mock_loggers
    log.do_default_logging_setup("hyperion.log", TEST_GRAYLOG_PORT, dev_mode=True)
    logger = log.LOGGER
    logger.info("test MX_Bluesky")
    DODAL_LOGGER.info("test_dodal")

    filehandler_calls = mock_filehandler_emit.mock_calls
    graylog_calls = mock_gelf_tcp_handler_emit.mock_calls

    assert len(filehandler_calls) >= 2
    assert len(graylog_calls) >= 2

    for handler in [filehandler_calls, graylog_calls]:
        handler_names = [c.args[0].name for c in handler]
        handler_messages = [c.args[0].message for c in handler]
        assert "MX-Bluesky" in handler_names
        assert "Dodal" in handler_names
        assert "test MX_Bluesky" in handler_messages
        assert "test_dodal" in handler_messages


@pytest.mark.parametrize("dev_mode", [True, False])
@pytest.mark.skip_log_setup
def test_callback_loggers_log_to_own_files(clear_and_mock_loggers, dev_mode: bool):
    mock_filehandler_emit, mock_gelf_tcp_handler_emit = clear_and_mock_loggers
    log.do_default_logging_setup("hyperion.log", TEST_GRAYLOG_PORT, dev_mode=True)

    hyperion_logger = log.LOGGER
    ispyb_zocalo_callback_logger = log.ISPYB_ZOCALO_CALLBACK_LOGGER
    nexus_logger = log.NEXUS_LOGGER
    logging_path, _ = log._get_logging_dirs(dev_mode)
    for logger in [ispyb_zocalo_callback_logger, nexus_logger]:
        set_up_all_logging_handlers(logger, logging_path, logger.name, True, 10000)

    hyperion_logger.info("test_hyperion")
    ispyb_zocalo_callback_logger.info("test_ispyb")
    nexus_logger.info("test_nexus")

    total_filehandler_calls = mock_filehandler_emit.mock_calls
    total_graylog_calls = mock_gelf_tcp_handler_emit.mock_calls

    assert len(total_filehandler_calls) == len(total_graylog_calls)

    hyperion_filehandler = next(
        filter(lambda h: isinstance(h, TimedRotatingFileHandler), DODAL_LOGGER.handlers)  # type: ignore
    )
    ispyb_filehandler = next(
        filter(
            lambda h: isinstance(h, TimedRotatingFileHandler),
            ispyb_zocalo_callback_logger.handlers,
        )  # type: ignore
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
    log.LOGGER.debug("debug_message_1")
    log.LOGGER.debug("debug_message_2")
    mock_filehandler_emit.assert_not_called()
    log.LOGGER.error("error happens")
    assert len(mock_filehandler_emit.mock_calls) == 4
    messages = [call.args[0].message for call in mock_filehandler_emit.mock_calls]
    assert "debug_message_1" in messages
    assert "debug_message_2" in messages
    assert "error happens" in messages


@pytest.mark.parametrize("dev_mode", [True, False])
@patch("mx_bluesky.common.utils.log.Path.mkdir")
def test_get_logging_dir_uses_env_var(mock_mkdir: MagicMock, dev_mode: bool):
    with patch.dict(os.environ, {"LOG_DIR": "test_dir", "DEBUG_LOG_DIR": "other_dir"}):
        assert log._get_logging_dirs(dev_mode) == (Path("test_dir"), Path("other_dir"))
        assert mock_mkdir.call_count == 2


@pytest.mark.parametrize(
    "dev_mode, expected_log_dir, expected_debug_log_dir",
    [
        [True, "/tmp/logs/bluesky/", "/tmp/logs/bluesky/"],
        [False, "/dls_sw/test/logs/bluesky/", "/dls/tmp/test/logs/bluesky/"],
    ],
)
@patch("mx_bluesky.common.utils.log.Path.mkdir")
def test_get_logging_dir_uses_beamline_if_no_dir_env_var(
    mock_mkdir: MagicMock,
    dev_mode: bool,
    expected_log_dir: str,
    expected_debug_log_dir: str,
):
    with patch.dict(os.environ, {"BEAMLINE": "test"}, clear=True):
        assert log._get_logging_dirs(dev_mode) == (
            Path(expected_log_dir),
            Path(expected_debug_log_dir),
        )
        assert mock_mkdir.call_count == 2


@pytest.mark.parametrize("dev_mode", [True, False])
@patch("mx_bluesky.common.utils.log.Path.mkdir")
def test_get_logging_dir_uses_tmp_if_no_env_var(mock_mkdir: MagicMock, dev_mode: bool):
    assert log._get_logging_dirs(dev_mode) == (
        Path("/tmp/logs/bluesky"),
        Path("/tmp/logs/bluesky"),
    )
    assert mock_mkdir.call_count == 2


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
