import os

from dodal.devices.detector import EIGER2_X_16M_SIZE
from pydantic.dataclasses import dataclass

from mx_bluesky.common.parameters.constants import (
    DeviceSettingsConstants,
    DocDescriptorNames,
    EnvironmentConstants,
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
    USE_GPU_RESULTS = True
    ALTERNATE_ROTATION_DIRECTION = True


@dataclass(frozen=True)
class HyperionConstants:
    ZOCALO_ENV = EnvironmentConstants.ZOCALO_ENV
    HARDWARE = HardwareConstants()
    PLAN = PlanNameConstants()
    WAIT = PlanGroupCheckpointConstants()
    HYPERION_PORT = 5005
    SUPERVISOR_PORT = 5006
    CALLBACK_0MQ_PROXY_PORTS = (5577, 5578)
    DESCRIPTORS = DocDescriptorNames()
    GRAYLOG_PORT = 12232  # Hyperion stream
    GRAYLOG_STREAM_ID = "66264f5519ccca6d1c9e4e03"
    PARAMETER_SCHEMA_DIRECTORY = "src/hyperion/parameters/schemas/"
    LOG_FILE_NAME = "hyperion.log"
    SUPERVISOR_LOG_FILE_NAME = "hyperion-supervisor.log"
    DEVICE_SETTINGS_CONSTANTS = DeviceSettingsConstants()
    DEFAULT_DETECTOR_DISTANCE_MM = 264.5


CONST = HyperionConstants()
