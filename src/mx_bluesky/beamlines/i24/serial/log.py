import functools
import logging
import logging.config
from os import environ
from pathlib import Path

from bluesky.log import logger as bluesky_logger
from dodal.log import (
    ERROR_LOG_BUFFER_LINES,
    get_graylog_configuration,
    ophyd_async_logger,
    set_up_DEBUG_memory_handler,
    set_up_graylog_handler,
    set_up_INFO_file_handler,
)
from dodal.log import LOGGER as dodal_logger

VISIT_PATH = Path("/dls_sw/i24/etc/ssx_current_visit.txt")


# Logging set up
logger = logging.getLogger("I24ssx")
logger.addHandler(logging.NullHandler())
logger.parent = dodal_logger

logging_config = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "class": "logging.Formatter",
            "format": "%(message)s",
        }
    },
    "handlers": {
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "default",
            "stream": "ext://sys.stdout",
        }
    },
    "loggers": {
        "I24ssx": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        }
    },
}

logging.config.dictConfig(logging_config)


def _read_visit_directory_from_file() -> Path:
    with open(VISIT_PATH) as f:
        visit = f.readline().rstrip()
    return Path(visit)


def _get_logging_file_path() -> Path:
    """Get the path to write the artemis log files to.
    If on a beamline, this will be written to the according area depending on the
    BEAMLINE envrionment variable. If no envrionment variable is found it will default
    it to the tmp/dev directory.
    Returns:
        logging_path (Path): Path to the log file for the file handler to write to.
    """
    beamline: str | None = environ.get("BEAMLINE")
    logging_path: Path

    if beamline:
        logging_path = _read_visit_directory_from_file() / "tmp/serial/logs"
    else:
        logging_path = Path("./tmp/logs/")

    Path(logging_path).mkdir(parents=True, exist_ok=True)
    return logging_path


def _integrate_bluesky_logs(parent_logger: logging.Logger):
    # Integrate only bluesky and ophyd_async logger
    for log in [bluesky_logger, ophyd_async_logger]:
        log.parent = dodal_logger
        log.setLevel(logging.DEBUG)


def default_logging_setup(dev_mode: bool = False):
    """ Default log setup for i24 serial.

    - Set up handlers for parent logger (from dodal): INFO file, DEBUG \
        memory and graylog.
    - integrate bluesky and ophyd loggers.
    """
    logging_path = _get_logging_file_path()
    set_up_INFO_file_handler(dodal_logger, logging_path, "dodal.log")
    set_up_DEBUG_memory_handler(
        dodal_logger, logging_path, "dodal.log", ERROR_LOG_BUFFER_LINES
    )
    set_up_graylog_handler(dodal_logger, *get_graylog_configuration(dev_mode, None))
    _integrate_bluesky_logs(dodal_logger)


def config(
    logfile: str | None = None,
    write_mode: str = "a",
    delayed: bool = False,
    dev_mode: bool = False,
):
    """
    Configure the logging.

    Args:
        logfile (str, optional): Filename for logfile. If passed, create a file handler\
            for the logger to write to file the log output. Defaults to None.
        write_mode (str, optional): String indicating writing mode for the output \
            .log file. Defaults to "a".
        dev_mode (bool, optional): If true, will log to graylog on localhost instead \
            of production. Defaults to False.
    """
    default_logging_setup(dev_mode=dev_mode)

    if logfile:
        logs = _get_logging_file_path() / logfile
        fileFormatter = logging.Formatter(
            "%(asctime)s %(levelname)s: \t(%(name)s) %(message)s",
            datefmt="%d-%m-%Y %I:%M:%S",
        )
        FH = logging.FileHandler(logs, mode=write_mode, encoding="utf-8", delay=delayed)
        FH.setLevel(logging.DEBUG)
        FH.setFormatter(fileFormatter)
        logger.addHandler(FH)


def log_on_entry(func):
    @functools.wraps(func)
    def decorator(*args, **kwargs):
        name = func.__name__
        logger.debug(f"Running {name} ")
        return func(*args, **kwargs)

    return decorator
