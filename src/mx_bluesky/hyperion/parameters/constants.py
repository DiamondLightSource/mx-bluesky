import os

from dodal.devices.detector import EIGER2_X_16M_SIZE
from pydantic.dataclasses import dataclass

from mx_bluesky.common.parameters.constants import (
    DeviceSettingsConstants,
    DocDescriptorNames,
    EnvironmentConstants,
    ExperimentParamConstants,
    FeatureSettings,
    FeatureSettingSources,
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
    OMEGA_FLIP = True
    ALTERNATE_ROTATION_DIRECTION = True


# These currently exist in GDA domain.properties
class HyperionFeatureSettingsSources(FeatureSettingSources):
    USE_GPU_RESULTS = "gda.mx.hyperion.xrc.use_gpu_results"
    USE_PANDA_FOR_GRIDSCAN = "gda.mx.hyperion.use_panda_for_gridscans"
    SET_STUB_OFFSETS = "gda.mx.hyperion.do_stub_offsets"
    PANDA_RUNUP_DISTANCE_MM = "gda.mx.hyperion.panda_runup_distance_mm"


# Use these defaults if we can't read from the config server
@dataclass
class HyperionFeatureSettings(FeatureSettings):
    USE_GPU_RESULTS: bool = True
    USE_PANDA_FOR_GRIDSCAN: bool = False
    SET_STUB_OFFSETS: bool = False
    PANDA_RUNUP_DISTANCE_MM: float = 0.16


@dataclass(frozen=True)
class HyperionConstants:
    ZOCALO_ENV = EnvironmentConstants.ZOCALO_ENV
    HARDWARE = HardwareConstants()
    I03 = I03Constants()
    PARAM = ExperimentParamConstants()
    PLAN = PlanNameConstants()
    WAIT = PlanGroupCheckpointConstants()
    HYPERION_PORT = 5005
    CALLBACK_0MQ_PROXY_PORTS = (5577, 5578)
    DESCRIPTORS = DocDescriptorNames()
    CONFIG_SERVER_URL = (
        "http://fake-url-not-real"
        if TEST_MODE
        else "https://daq-config.diamond.ac.uk/api"
    )
    GRAYLOG_PORT = 12232  # Hyperion stream
    GRAYLOG_STREAM_ID = "66264f5519ccca6d1c9e4e03"
    PARAMETER_SCHEMA_DIRECTORY = "src/hyperion/parameters/schemas/"
    LOG_FILE_NAME = "hyperion.log"
    DEVICE_SETTINGS_CONSTANTS = DeviceSettingsConstants()


CONST = HyperionConstants()
