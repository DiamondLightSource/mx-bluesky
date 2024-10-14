import functools
import logging
import logging.config
from os import environ
from pathlib import Path

from dodal.log import (
    ERROR_LOG_BUFFER_LINES,
    integrate_bluesky_and_ophyd_logging,
    set_up_all_logging_handlers,
)
from dodal.log import LOGGER as dodal_logger

VISIT_PATH = Path("/dls_sw/i24/etc/ssx_current_visit.txt")


class OphydDebugFilter(logging.Filter):  # NOTE yet to be fully tested
    """Do not send ophyd debug log messages to stream handler."""

    def filter(self, record):
        return "ophyd" not in record.getMessage().lower()


# Logging set up
logger = logging.getLogger("I24ssx")
logger.addHandler(logging.NullHandler())
logger.parent = dodal_logger

logging_config = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "ophyd_filter": {
            "()": OphydDebugFilter,
        }
    },
    "formatters": {
        "default": {
            "class": "logging.Formatter",
            "format": "%(message)s",
        }
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "default",
            "filters": ["ophyd_filter"],
            "stream": "ext://sys.stdout",
        }
    },
    "loggers": {
        "I24ssx": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": True,
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


def default_logging_setup(dev_mode: bool = False):
    """ Default log setup for i24 serial.

    - Set up handlers for parent logger (from dodal)
    - integrate bluesky and ophyd loggers
    - Remove dodal stream handler to avoid double messages (for now, use only the \
        i24ssx default stream to keep the output expected by the scientists.)
    """
    handlers = set_up_all_logging_handlers(  # noqa: F841
        dodal_logger,
        _get_logging_file_path(),
        "dodal.log",
        dev_mode,
        ERROR_LOG_BUFFER_LINES,
    )
    integrate_bluesky_and_ophyd_logging(dodal_logger)
    # Remove dodal StreamHandler to avoid duplication of messages above debug
    dodal_logger.removeHandler(dodal_logger.handlers[0])


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
