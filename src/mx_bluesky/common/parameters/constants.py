import os

from dodal.devices.aperturescatterguard import ApertureValue
from pydantic.dataclasses import dataclass

TEST_MODE = os.environ.get("HYPERION_TEST_MODE")  # Environment name will be updated in
# https://github.com/DiamondLightSource/mx-bluesky/issues/214


@dataclass(frozen=True)
class DocDescriptorNames:
    # Robot load event descriptor
    ROBOT_LOAD = "robot_load"
    # For callbacks to use
    OAV_ROTATION_SNAPSHOT_TRIGGERED = "rotation_snapshot_triggered"
    OAV_GRID_SNAPSHOT_TRIGGERED = "snapshot_to_ispyb"
    HARDWARE_READ_PRE = "read_hardware_for_callbacks_pre_collection"
    HARDWARE_READ_DURING = "read_hardware_for_callbacks_during_collection"
    ZOCALO_HW_READ = "zocalo_read_hardware_plan"


@dataclass(frozen=True)
class PlanNameConstants:
    DO_FGS = "do_fgs"


@dataclass(frozen=True)
class TriggerConstants:
    ZOCALO = "trigger_zocalo_on"


@dataclass(frozen=True)
class HardwareConstants:
    OAV_REFRESH_DELAY = 0.3


@dataclass(frozen=True)
class GridscanParamConstants:
    WIDTH_UM = 600.0
    EXPOSURE_TIME_S = 0.004
    USE_ROI = True
    BOX_WIDTH_UM = 20.0
    OMEGA_1 = 0.0
    OMEGA_2 = 90.0


@dataclass(frozen=True)
class RotationParamConstants:
    DEFAULT_APERTURE_POSITION = ApertureValue.LARGE


@dataclass(frozen=True)
class DetectorParamConstants:
    BEAM_XY_LUT_PATH = (
        "tests/test_data/test_det_dist_converter.txt"
        if TEST_MODE
        else "/dls_sw/i03/software/daq_configuration/lookup/DetDistToBeamXYConverter.txt"
    )


@dataclass(frozen=True)
class ExperimentParamConstants:
    DETECTOR = DetectorParamConstants()
    GRIDSCAN = GridscanParamConstants()
    ROTATION = RotationParamConstants()


@dataclass(frozen=True)
class PlanGroupCheckpointConstants:
    # For places to synchronise / stop and wait in plans, use as bluesky group names
    GRID_READY_FOR_DC = "grid_ready_for_data_collection"
    ROTATION_READY_FOR_DC = "rotation_ready_for_data_collection"
    MOVE_GONIO_TO_START = "move_gonio_to_start"
    READY_FOR_OAV = "ready_for_oav"


@dataclass(frozen=True)
class SimConstants:
    BEAMLINE = "BL03S"
    INSERTION_PREFIX = "SR03S"
    ZOCALO_ENV = "dev_artemis"
    # this one is for unit tests
    ISPYB_CONFIG = "tests/test_data/test_config.cfg"
    # this one is for system tests
    DEV_ISPYB_DATABASE_CFG = "/dls_sw/dasc/mariadb/credentials/ispyb-hyperion-dev.cfg"


# Maybe this shouldn't be a thing and the mx params shouldn't have defaults so that beamlines are forced to think about their values
@dataclass(frozen=True)
class MxDefaultConstants:
    DESCRIPTORS = DocDescriptorNames()
    TRIGGER = TriggerConstants()
    ZOCALO_ENV = "dev_artemis" if TEST_MODE else "artemis"
    HARDWARE = HardwareConstants()
    PARAM = ExperimentParamConstants()
    PLAN = PlanNameConstants()
    WAIT = PlanGroupCheckpointConstants()
    SIM = SimConstants()
    TRIGGER = TriggerConstants()
    DESCRIPTORS = DocDescriptorNames()
    CONFIG_SERVER_URL = (
        "http://fake-url-not-real"
        if TEST_MODE
        else "https://daq-config.diamond.ac.uk/api"
    )
    GRAYLOG_PORT = 12232
    PARAMETER_SCHEMA_DIRECTORY = (
        "src/mx_bluesky/common/parameters/schemas/"  # TODO make this
    )
    ZOCALO_ENV = "dev_artemis" if TEST_MODE else "artemis"
    LOG_FILE_NAME = "mx-bluesky.log"


CONST = MxDefaultConstants()
