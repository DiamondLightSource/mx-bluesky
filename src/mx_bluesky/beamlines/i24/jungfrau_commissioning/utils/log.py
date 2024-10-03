import logging
import os
from pathlib import Path

from dodal.log import LOGGER as dodal_logger
from dodal.log import set_up_all_logging_handlers as setup_dodal_logging

LOGGER = logging.getLogger("jungfrau_commissioning")
LOGGER.setLevel(logging.DEBUG)
LOGGER.parent = dodal_logger

logging_directory = "/tmp/jungfrau_commissioning_logs_ffv81422"


def set_up_logging_handlers(dev_mode: bool = True):
    """Set up the logging level and instances for user chosen level of logging.

    Mode defaults to production and can be switched to dev with the --dev flag on run.
    """
    if not os.path.isdir(logging_directory):
        os.makedirs(logging_directory)
    handlers = setup_dodal_logging(
        LOGGER, Path(logging_directory), "log.log", dev_mode, 20000
    )

    return handlers
