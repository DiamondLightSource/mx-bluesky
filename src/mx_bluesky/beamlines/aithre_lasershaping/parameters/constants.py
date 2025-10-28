import os

from pydantic.dataclasses import dataclass

TEST_MODE = os.environ.get("AITHRE_TEST_MODE")


@dataclass(frozen=True)
class AithreConstants:
    BEAMLINE = "aithre"
    OAV_CENTRING_FILE = (
        # "/dls/science/groups/i23/aithre/daq_configuration/json/OAVCentring_aithre.json"
        "/dls/science/users/wck38436/OAVCentring_aithre.json"
    )
    LOG_FILE_NAME = "aithre.log"


CONST = AithreConstants()
