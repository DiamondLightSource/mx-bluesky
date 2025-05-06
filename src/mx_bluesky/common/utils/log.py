import logging
from logging.handlers import TimedRotatingFileHandler
from os import environ
from pathlib import Path

from dodal.log import (
    ERROR_LOG_BUFFER_LINES,
    CircularMemoryHandler,
    DodalLogHandlers,
    integrate_bluesky_and_ophyd_logging,
    set_up_all_logging_handlers,
)
from dodal.log import LOGGER as dodal_logger

LOGGER = logging.getLogger("MX-Bluesky")
LOGGER.setLevel("DEBUG")
LOGGER.parent = dodal_logger

ISPYB_ZOCALO_CALLBACK_LOGGER = logging.getLogger("ISPyB and Zocalo callbacks")
ISPYB_ZOCALO_CALLBACK_LOGGER.setLevel(logging.DEBUG)

NEXUS_LOGGER = logging.getLogger("NeXus callbacks")
NEXUS_LOGGER.setLevel(logging.DEBUG)

ALL_LOGGERS = [LOGGER, ISPYB_ZOCALO_CALLBACK_LOGGER, NEXUS_LOGGER]

__logger_handlers: DodalLogHandlers | None = None


class ExperimentMetadataTagFilter(logging.Filter):
    """When an instance of this custom filter is added to a logging handler, dc_group_id
    and run_id will be tagged in that handlers' log messages."""

    dc_group_id: str | None = None
    run_uid: str | None = None

    def filter(self, record):
        if self.dc_group_id:
            record.dc_group_id = self.dc_group_id
        if self.run_uid:
            record.run_uid = self.run_uid
        return True


tag_filter = ExperimentMetadataTagFilter()


def set_dcgid_tag(dcgid):
    """Set the datacollection group id as a tag on all subsequent log messages.
    Setting to None will remove the tag."""
    tag_filter.dc_group_id = dcgid


def set_uid_tag(uid):
    """Set the unique id as a tag on all subsequent log messages.
    Setting to None will remove the tag."""
    tag_filter.run_uid = uid


def do_default_logging_setup(
    file_name: str,
    graylog_port: int,
    dev_mode: bool = False,
    integrate_all_logs: bool = True,
):
    """Configures dodal logger so that separate debug and info log files are created,
    info logs are sent to Graylog, info logs are streamed to sys.sterr, and logs from ophyd
    and bluesky and ophyd-async are optionally included."""
    logging_path, debug_logging_path = _get_logging_dirs()
    handlers = set_up_all_logging_handlers(
        dodal_logger,
        logging_path,
        file_name,
        dev_mode,
        ERROR_LOG_BUFFER_LINES,
        graylog_port,
        debug_logging_path,
    )

    if integrate_all_logs:
        integrate_bluesky_and_ophyd_logging(dodal_logger)

    handlers["graylog_handler"].addFilter(tag_filter)

    global __logger_handlers
    __logger_handlers = handlers


def _get_debug_handler() -> CircularMemoryHandler:
    assert __logger_handlers is not None, (
        "You can only use this after running the default logging setup"
    )
    return __logger_handlers["debug_memory_handler"]


def flush_debug_handler() -> str:
    """Writes the contents of the circular debug log buffer to disk and returns the written filename"""
    handler = _get_debug_handler()
    assert isinstance(handler.target, TimedRotatingFileHandler), (
        "Circular memory handler doesn't have an appropriate fileHandler target"
    )
    handler.flush()
    return handler.target.baseFilename


def _get_logging_dirs() -> tuple[Path, Path]:
    """Get the paths to write the mx_bluesky log files to.

    Log location can be specified in the LOG_DIR environment variable, otherwise MX bluesky logs are written to 'dls_sw/ixx/logs/bluesky'.
    This directory will be created if it is not found

    Logs are written to ./tmp/logs/bluesky if BEAMLINE environment variable is not found

    Returns:
        tuple[Path, Path]: Paths to the standard log file and to the debug log file, for the file handlers to write to
    """

    logging_str = environ.get("LOG_DIR")
    beamline = environ.get("BEAMLINE")
    if logging_str:
        logging_path = Path(logging_str)
        debug_logging_path = logging_path
    elif beamline:
        logging_path = Path(f"/dls_sw/{beamline}/logs/bluesky/")
        debug_logging_path = Path(f"/dls/tmp/{beamline}/logs/bluesky/")
    else:
        logging_path = Path("/tmp/logs/bluesky")
        debug_logging_path = logging_path
    Path.mkdir(logging_path, exist_ok=True, parents=True)
    Path.mkdir(debug_logging_path, exist_ok=True, parents=True)
    return logging_path, debug_logging_path
