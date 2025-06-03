from dataclasses import dataclass


@dataclass(frozen=True)
class I04Constants:
    GRAYLOG_PORT = 12232
    LOG_FILE_NAME = "i04.log"


CONST = I04Constants()
