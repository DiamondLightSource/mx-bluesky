import os

from dodal.devices.detector import EIGER2_X_16M_SIZE
from pydantic.dataclasses import dataclass

from mx_bluesky.common.parameters.constants import (
    DeviceSettingsConstants,
    DocDescriptorNames,
    EnvironmentConstants,
    ExperimentParamConstants,
    HardwareConstants,
    OavConstants,
    PlanGroupCheckpointConstants,
    PlanNameConstants,
)

TEST_MODE = os.environ.get("HYPERION_TEST_MODE")


@dataclass(frozen=True)
class I03Constants:
    BEAMLINE = "BL03S" if TEST_MODE else "BL03I"
    DETECTOR = EIGER2_X_16M_SIZE
    INSERTION_PREFIX = "SR03S" if TEST_MODE else "SR03I"
    OAV_CENTRING_FILE = OavConstants.OAV_CONFIG_JSON
    SHUTTER_TIME_S = 0.06
    USE_PANDA_FOR_GRIDSCAN = False
    SET_STUB_OFFSETS = False
    OMEGA_FLIP = True
    ALTERNATE_ROTATION_DIRECTION = True

    # Turns on GPU processing for zocalo and uses the results that come back
    USE_GPU_RESULTS = True


@dataclass(frozen=True)
class HyperionConstants:
    DESCRIPTORS = DocDescriptorNames()
    ZOCALO_ENV = EnvironmentConstants.ZOCALO_ENV
    HARDWARE = HardwareConstants()
    I03 = I03Constants()
    PARAM = ExperimentParamConstants()
    PLAN = PlanNameConstants()
    WAIT = PlanGroupCheckpointConstants()
    CALLBACK_0MQ_PROXY_PORTS = (5577, 5578)
    DESCRIPTORS = DocDescriptorNames()
    CONFIG_SERVER_URL = (
        "http://fake-url-not-real"
        if TEST_MODE
        else "https://daq-config.diamond.ac.uk/api"
    )
    GRAYLOG_PORT = 12232
    PARAMETER_SCHEMA_DIRECTORY = "src/hyperion/parameters/schemas/"
    LOG_FILE_NAME = "hyperion.log"
    DEVICE_SETTINGS_CONSTANTS = DeviceSettingsConstants()


CONST = HyperionConstants()
