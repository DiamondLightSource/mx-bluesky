import os

from dodal.devices.detector import EIGER2_X_16M_SIZE
from pydantic.dataclasses import dataclass

from mx_bluesky.common.parameters.constants import (
    DocDescriptorNames,
    ExperimentParamConstants,
    HardwareConstants,
    PlanGroupCheckpointConstants,
    PlanNameConstants,
    SimConstants,
    TriggerConstants,
)

TEST_MODE = os.environ.get("HYPERION_TEST_MODE")

_test_oav_file = "tests/test_data/test_OAVCentring.json"
_live_oav_file = "/dls_sw/i03/software/daq_configuration/json/OAVCentring_hyperion.json"


@dataclass(frozen=True)
class I03Constants:
    BASE_DATA_DIR = "/tmp/dls/i03/data/" if TEST_MODE else "/dls/i03/data/"
    BEAMLINE = "BL03S" if TEST_MODE else "BL03I"
    DETECTOR = EIGER2_X_16M_SIZE
    INSERTION_PREFIX = "SR03S" if TEST_MODE else "SR03I"
    OAV_CENTRING_FILE = _test_oav_file if TEST_MODE else _live_oav_file
    SHUTTER_TIME_S = 0.06
    USE_PANDA_FOR_GRIDSCAN = False
    THAWING_TIME = 20
    SET_STUB_OFFSETS = False

    # Turns on GPU processing for zocalo and logs a comparison between GPU and CPU-
    # processed results. GPU results never used in analysis for now
    COMPARE_CPU_AND_GPU_ZOCALO = False


@dataclass(frozen=True)
class HyperionConstants:
    DESCRIPTORS = DocDescriptorNames()
    TRIGGER = TriggerConstants()
    ZOCALO_ENV = "dev_artemis" if TEST_MODE else "artemis"
    HARDWARE = HardwareConstants()
    I03 = I03Constants()
    PARAM = ExperimentParamConstants()
    PLAN = PlanNameConstants()
    WAIT = PlanGroupCheckpointConstants()
    SIM = SimConstants()
    TRIGGER = TriggerConstants()
    CALLBACK_0MQ_PROXY_PORTS = (5577, 5578)
    DESCRIPTORS = DocDescriptorNames()
    CONFIG_SERVER_URL = (
        "http://fake-url-not-real"
        if TEST_MODE
        else "https://daq-config.diamond.ac.uk/api"
    )
    GRAYLOG_PORT = 12232
    PARAMETER_SCHEMA_DIRECTORY = "src/hyperion/parameters/schemas/"
    ZOCALO_ENV = "dev_artemis" if TEST_MODE else "artemis"
    LOG_FILE_NAME = "hyperion.log"


CONST = HyperionConstants()
