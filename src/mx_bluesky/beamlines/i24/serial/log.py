import functools
import logging
import logging.config
import time
from os import environ
from pathlib import Path

import bluesky.plan_stubs as bps
from bluesky.log import logger as bluesky_logger
from bluesky.utils import MsgGenerator
from dodal.log import DEFAULT_GRAYLOG_PORT, ophyd_async_logger
from dodal.log import LOGGER as dodal_logger

from mx_bluesky.common.utils.log import do_default_logging_setup

VISIT_PATH = Path("/dls_sw/i24/etc/ssx_current_visit.txt")


# Logging set up
SSX_LOGGER = logging.getLogger("I24serial")
SSX_LOGGER.addHandler(logging.NullHandler())
SSX_LOGGER.parent = dodal_logger


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
        "I24serial": {
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
    """Get the path to write the serial experiment specific log file to.
    If on a beamline, this will be written to the tmp folder in the current visit.
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
        log.parent = parent_logger
        log.setLevel(logging.DEBUG)


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
    if logfile:
        logs = _get_logging_file_path() / logfile
        fileFormatter = logging.Formatter(
            "%(asctime)s %(levelname)s: \t(%(name)s) %(message)s",
            datefmt="%d-%m-%Y %I:%M:%S",
        )
        FH = logging.FileHandler(logs, mode=write_mode, encoding="utf-8", delay=delayed)
        FH.setLevel(logging.DEBUG)
        FH.setFormatter(fileFormatter)
        SSX_LOGGER.addHandler(FH)
    do_default_logging_setup(
        "mx-bluesky.log",
        DEFAULT_GRAYLOG_PORT,
        dev_mode=dev_mode,
        integrate_all_logs=False,
    )
    # Remove dodal StreamHandler to avoid duplication of messages above debug
    dodal_logger.removeHandler(dodal_logger.handlers[0])
    _integrate_bluesky_logs(dodal_logger)


def log_on_entry(func):
    @functools.wraps(func)
    def decorator(*args, **kwargs):
        name = func.__name__
        SSX_LOGGER.debug(f"Running {name} ")
        return func(*args, **kwargs)

    return decorator


def setup_collection_logs(expt: str, dev_mode: bool = False) -> MsgGenerator:
    """A small plan to set up the logging from blueapi on start up as we're running \
        on procserv.
        This setup will likely change once the beamline has a cluster.
    """
    if (
        expt == "Serial Fixed"
    ):  # SSXType.FIXED: See https://github.com/DiamondLightSource/mx-bluesky/issues/608
        logfile = time.strftime("i24fixedtarget_%d%B%y.log").lower()
    else:
        logfile = time.strftime("i24extruder_%d%B%y.log").lower()

    config(logfile, dev_mode=dev_mode)
    yield from bps.null()


def clean_up_log_config_at_end() -> MsgGenerator:
    """A small plan for blueapi to tidy up logging configuration."""
    # See https://github.com/DiamondLightSource/mx-bluesky/issues/609
    for handler in SSX_LOGGER.handlers:
        SSX_LOGGER.removeHandler(handler)
    for handler in dodal_logger.handlers:
        dodal_logger.removeHandler(handler)
    yield from bps.null()
