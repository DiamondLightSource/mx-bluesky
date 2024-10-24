import logging

from dodal.log import LOGGER as dodal_logger

LOGGER = logging.getLogger("Hyperion")
LOGGER.setLevel("DEBUG")
LOGGER.parent = dodal_logger

ISPYB_LOGGER = logging.getLogger("Hyperion ISPyB and Zocalo callbacks")
ISPYB_LOGGER.setLevel(logging.DEBUG)

NEXUS_LOGGER = logging.getLogger("Hyperion NeXus callbacks")
NEXUS_LOGGER.setLevel(logging.DEBUG)

ALL_LOGGERS = [LOGGER, ISPYB_LOGGER, NEXUS_LOGGER]
