from pydantic.dataclasses import dataclass

from mx_bluesky.common.parameters.constants import (
    TEST_MODE,
    BeamlineConstants,
)


@dataclass(frozen=True)
class i04Constants(BeamlineConstants):
    # I04 = I04Constants()
    CALLBACK_0MQ_PROXY_PORTS = (5577, 5578)
    CONFIG_SERVER_URL = (
        "http://fake-url-not-real"
        if TEST_MODE
        else "https://daq-config.diamond.ac.uk/api"
    )
    GRAYLOG_PORT = 12232
    LOG_FILE_NAME = "i04.log"


CONST = i04Constants()
