import logging
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mx_bluesky.beamlines.i24.serial import log


@pytest.fixture
def dummy_logger():
    logger = logging.getLogger("I24serial")
    yield logger


def _destroy_handlers(logger):
    for handler in logger.handlers:
        handler.close()
    logger.handlers.clear()


@patch("mx_bluesky.beamlines.i24.serial.log.environ")
@patch("mx_bluesky.beamlines.i24.serial.log.Path.mkdir")
def test_logging_file_path(mock_dir, mock_environ):
    mock_environ.get.return_value = None
    log_path = log._get_logging_file_path()
    assert mock_dir.call_count == 1
    assert log_path.as_posix() == "tmp/logs"


@patch("mx_bluesky.beamlines.i24.serial.log._read_visit_directory_from_file")
@patch("mx_bluesky.beamlines.i24.serial.log.environ")
@patch("mx_bluesky.beamlines.i24.serial.log.Path.mkdir")
def test_logging_file_path_on_beamline(mock_dir, mock_environ, mock_visit):
    mock_environ.get.return_value = "i24"
    mock_visit.return_value = Path("/path/to/i24/data")
    log_path = log._get_logging_file_path()
    assert mock_dir.call_count == 1
    assert log_path.as_posix() == "/path/to/i24/data/tmp/serial/logs"


def test_basic_logging_config(dummy_logger):
    assert dummy_logger.hasHandlers() is True
    assert len(dummy_logger.handlers) == 1
    assert dummy_logger.handlers[0].level == logging.INFO


def test_integrate_bluesky_logs():
    mock_dodal_logger = MagicMock()
    with (
        patch("mx_bluesky.beamlines.i24.serial.log.bluesky_logger") as mock_bluesky_log,
        patch(
            "mx_bluesky.beamlines.i24.serial.log.ophyd_async_logger"
        ) as mock_ophyd_log,
    ):
        log._integrate_bluesky_logs(mock_dodal_logger)
        assert mock_bluesky_log.parent == mock_dodal_logger
        assert mock_ophyd_log.parent == mock_dodal_logger


@patch("mx_bluesky.beamlines.i24.serial.log.Path.mkdir")
@patch("mx_bluesky.beamlines.i24.serial.log.do_default_logging_setup")
@patch("mx_bluesky.beamlines.i24.serial.log._integrate_bluesky_logs")
def test_logging_config_with_filehandler(
    mock_integrate_logs, mock_default, mock_dir, dummy_logger
):
    with patch("mx_bluesky.beamlines.i24.serial.log.dodal_logger") as mock_dodal_logger:
        log.config("dummy.log", delayed=True, dev_mode=True)
        assert len(dummy_logger.handlers) == 2
        mock_default.assert_called_once()
        mock_integrate_logs.assert_called_once_with(mock_dodal_logger)
        assert mock_dodal_logger.removeHandler.call_count == 1
        assert mock_dir.call_count == 1
        assert dummy_logger.handlers[1].level == logging.DEBUG
        # Clear FileHandler to avoid other tests failing if it is kept open
        dummy_logger.removeHandler(dummy_logger.handlers[1])
        _destroy_handlers(dummy_logger.parent)


@patch("mx_bluesky.beamlines.i24.serial.log.config")
def test_setup_collection_logs_in_dev_mode(mock_config, RE):
    # Fixed target, dev mode
    fake_filename = time.strftime("i24fixedtarget_%d%B%y.log").lower()
    RE(log.setup_collection_logs("Serial Fixed", True))

    mock_config.assert_called_once_with(fake_filename, dev_mode=True)


@patch("mx_bluesky.beamlines.i24.serial.log.config")
def test_setup_collection_logs(mock_config, RE):
    # Extruder, non dev mode
    fake_filename = time.strftime("i24extruder_%d%B%y.log").lower()
    RE(log.setup_collection_logs("Serial Jet"))

    mock_config.assert_called_once_with(fake_filename, dev_mode=False)


def test_clean_up_log(dummy_logger, RE):
    with patch("mx_bluesky.beamlines.i24.serial.log.dodal_logger") as mock_dodal_logger:
        RE(log.clean_up_log_config_at_end())

        assert len(dummy_logger.handlers) == 0
        assert len(mock_dodal_logger.handlers) == 0
