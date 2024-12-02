from enum import Enum

from dodal.devices.aperturescatterguard import ApertureValue
from dodal.devices.detector import EIGER2_X_16M_SIZE
from dodal.devices.zocalo.zocalo_constants import ZOCALO_ENV as ZOCALO_ENV_FROM_DODAL
from dodal.utils import get_beamline_name
from pydantic.dataclasses import dataclass

BEAMLINE = get_beamline_name("test")
TEST_MODE = BEAMLINE == "test"


@dataclass(frozen=True)
class DocDescriptorNames:
    # Robot load event descriptor
    ROBOT_LOAD = "robot_load"
    # For callbacks to use
    OAV_ROTATION_SNAPSHOT_TRIGGERED = "rotation_snapshot_triggered"
    OAV_GRID_SNAPSHOT_TRIGGERED = "snapshot_to_ispyb"
    HARDWARE_READ_PRE = "read_hardware_for_callbacks_pre_collection"
    HARDWARE_READ_DURING = "read_hardware_for_callbacks_during_collection"
    SAMPLE_HANDLING_EXCEPTION = "sample_handling_exception"
    ZOCALO_HW_READ = "zocalo_read_hardware_plan"
    FLYSCAN_RESULTS = "flyscan_results_obtained"


@dataclass(frozen=True)
class OavConstants:
    OAV_CONFIG_JSON = (
        "tests/test_data/test_OAVCentring.json"
        if TEST_MODE
        else (
            f"/dls_sw/{BEAMLINE}/software/daq_configuration/json/OAVCentring_hyperion.json"
        )
    )


@dataclass(frozen=True)
class PlanNameConstants:
    LOAD_CENTRE_COLLECT = "load_centre_collect"
    # Robot load subplan
    ROBOT_LOAD = "robot_load"
    # Gridscan
    GRID_DETECT_AND_DO_GRIDSCAN = "grid_detect_and_do_gridscan"
    GRID_DETECT_INNER = "grid_detect"
    GRIDSCAN_OUTER = "run_gridscan_move_and_tidy"
    GRIDSCAN_AND_MOVE = "run_gridscan_and_move"
    GRIDSCAN_MAIN = "run_gridscan"
    DO_FGS = "do_fgs"
    # IspyB callback activation
    ISPYB_ACTIVATION = "ispyb_activation"
    ROBOT_LOAD_AND_SNAPSHOTS = "robot_load_and_snapshots"
    # Rotation scan
    ROTATION_MULTI = "multi_rotation_wrapper"
    ROTATION_OUTER = "rotation_scan_with_cleanup"
    ROTATION_MAIN = "rotation_scan_main"
    FLYSCAN_RESULTS = "xray_centre_results"


@dataclass(frozen=True)
class EnvironmentConstants:
    ZOCALO_ENV = ZOCALO_ENV_FROM_DODAL


@dataclass(frozen=True)
class TriggerConstants:
    ZOCALO = "trigger_zocalo_on"


@dataclass(frozen=True)
class HardwareConstants:
    OAV_REFRESH_DELAY = 0.3
    PANDA_FGS_RUN_UP_DEFAULT = 0.17
    CRYOJET_MARGIN_MM = 0.2
    THAWING_TIME = 20


@dataclass(frozen=True)
class GridscanParamConstants:
    WIDTH_UM = 600.0
    EXPOSURE_TIME_S = 0.004
    USE_ROI = True
    BOX_WIDTH_UM = 20.0
    OMEGA_1 = 0.0
    OMEGA_2 = 90.0
    PANDA_RUN_UP_DISTANCE_MM = 0.2


@dataclass(frozen=True)
class RotationParamConstants:
    DEFAULT_APERTURE_POSITION = ApertureValue.LARGE


@dataclass(frozen=True)
class DetectorParamConstants:
    BEAM_XY_LUT_PATH = (
        "tests/test_data/test_det_dist_converter.txt"
        if TEST_MODE
        else f"/dls_sw/{BEAMLINE}/software/daq_configuration/lookup/DetDistToBeamXYConverter.txt"
    )
    DETECTOR = EIGER2_X_16M_SIZE


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
    # this one is for unit tests
    ISPYB_CONFIG = "tests/test_data/test_config.cfg"
    # this one is for system tests
    DEV_ISPYB_DATABASE_CFG = "/dls_sw/dasc/mariadb/credentials/ispyb-hyperion-dev.cfg"


class Actions(Enum):
    START = "start"
    STOP = "stop"
    SHUTDOWN = "shutdown"
    STATUS = "status"


class Status(Enum):
    WARN = "Warn"
    FAILED = "Failed"
    SUCCESS = "Success"
    BUSY = "Busy"
    ABORTING = "Aborting"
    IDLE = "Idle"
