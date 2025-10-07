import os

from pydantic.dataclasses import dataclass

# from mx_bluesky.common.parameters.constants import (
#    OavConstants,
# )

TEST_MODE = os.environ.get("AITHRE_TEST_MODE")


@dataclass(frozen=True)
class AithreConstants:
    BEAMLINE = "aithre"
    #    OAV_CENTRING_FILE = OavConstants.OAV_CONFIG_JSON
    OAV_CENTRING_FILE = (
        "/dls/science/groups/i23/aithre/daq_configuration/json/OAVCentring_aithre.json"
    )
    LOG_FILE_NAME = "aithre.log"


CONST = AithreConstants()
