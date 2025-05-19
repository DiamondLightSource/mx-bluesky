import os
from enum import Enum

from dodal.devices.aperturescatterguard import ApertureValue
from dodal.devices.detector import EIGER2_X_16M_SIZE
from dodal.devices.zocalo.zocalo_constants import ZOCALO_ENV as ZOCALO_ENV_FROM_DODAL
from dodal.utils import get_beamline_name
from pydantic.dataclasses import dataclass

from mx_bluesky.definitions import ROOT_DIR

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
    ROTATION_MULTI_OUTER = "multi_rotation_outer"
    ROTATION_OUTER = "rotation_scan_with_cleanup"
    ROTATION_MAIN = "rotation_scan_main"
    FLYSCAN_RESULTS = "xray_centre_results"
    SET_ENERGY = "set_energy"
    UNNAMED_RUN = "unnamed_run"


@dataclass(frozen=True)
class EnvironmentConstants:
    ZOCALO_ENV = ZOCALO_ENV_FROM_DODAL


@dataclass(frozen=True)
class HardwareConstants:
    OAV_REFRESH_DELAY = 0.3
    PANDA_FGS_RUN_UP_DEFAULT = 0.17
    CRYOJET_MARGIN_MM = 0.2
    THAWING_TIME = 40
    TIP_OFFSET_UM = 0

    # Value quoted in https://www.dectris.com/en/detectors/x-ray-detectors/eiger2/eiger2-for-synchrotrons/eiger2-x/,
    # causes dropped frames, so increase value for safety
    PANDA_FGS_EIGER_DEADTIME_S = 5e-5


@dataclass(frozen=True)
class GridscanParamConstants:
    WIDTH_UM = 600.0
    EXPOSURE_TIME_S = 0.004
    USE_ROI = True
    BOX_WIDTH_UM = 20.0
    OMEGA_1 = 0.0
    OMEGA_2 = 90.0
    PANDA_RUN_UP_DISTANCE_MM = 0.2
    ZOCALO_MIN_TOTAL_COUNT_THRESHOLD = 3


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
    PREPARE_APERTURE = "prepare_aperture"


# Eventually replace below with https://github.com/DiamondLightSource/mx-bluesky/issues/798
@dataclass(frozen=True)
class DeviceSettingsConstants:
    PANDA_FLYSCAN_SETTINGS_FILENAME = "panda-gridscan"
    PANDA_FLYSCAN_SETTINGS_DIR = os.path.abspath(
        f"{ROOT_DIR}/hyperion/resources/panda/"
    )


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
