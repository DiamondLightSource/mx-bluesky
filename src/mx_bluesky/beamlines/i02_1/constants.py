from pydantic.dataclasses import dataclass


@dataclass(frozen=True)
class I02_1_Constants:
    GRAYLOG_PORT = 12232
    LOG_FILE_NAME = "i02_1_bluesky.log"
