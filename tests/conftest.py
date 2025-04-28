import asyncio
import gzip
import json
import logging
import os
import sys
import threading
from collections.abc import Callable, Generator, Sequence
from contextlib import ExitStack
from copy import deepcopy
from functools import partial
from types import ModuleType
from typing import Any
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import numpy
import pydantic
import pytest
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator
from bluesky.utils import Msg
from dodal.beamlines import i03
from dodal.common.beamlines import beamline_utils
from dodal.common.beamlines.beamline_parameters import (
    GDABeamlineParameters,
)
from dodal.common.beamlines.beamline_utils import clear_devices
from dodal.devices.aperturescatterguard import (
    AperturePosition,
    ApertureScatterguard,
    ApertureValue,
)
from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
from dodal.devices.backlight import Backlight
from dodal.devices.detector.detector_motion import DetectorMotion
from dodal.devices.eiger import EigerDetector
from dodal.devices.fast_grid_scan import FastGridScanCommon
from dodal.devices.flux import Flux
from dodal.devices.i03 import Beamstop, BeamstopPositions
from dodal.devices.i03.dcm import DCM
from dodal.devices.oav.oav_detector import OAV, OAVConfig
from dodal.devices.oav.oav_parameters import OAVParameters
from dodal.devices.oav.pin_image_recognition import PinTipDetection
from dodal.devices.robot import BartRobot
from dodal.devices.s4_slit_gaps import S4SlitGaps
from dodal.devices.smargon import Smargon
from dodal.devices.synchrotron import Synchrotron, SynchrotronMode
from dodal.devices.thawer import Thawer
from dodal.devices.undulator import Undulator
from dodal.devices.util.test_utils import patch_motor
from dodal.devices.webcam import Webcam
from dodal.devices.xbpm_feedback import XBPMFeedback
from dodal.devices.zebra.zebra import ArmDemand, Zebra
from dodal.devices.zebra.zebra_controlled_shutter import ZebraShutter
from dodal.devices.zocalo import ZocaloResults
from dodal.log import LOGGER as dodal_logger
from dodal.log import set_up_all_logging_handlers
from dodal.utils import AnyDeviceFactory, collect_factories
from event_model.documents import Event, EventDescriptor, RunStart, RunStop
from ispyb.sp.mxacquisition import MXAcquisition
from ophyd.sim import NullStatus
from ophyd_async.core import (
    AsyncStatus,
    Device,
    DeviceVector,
)
from ophyd_async.epics.core import epics_signal_rw
from ophyd_async.epics.motor import Motor
from ophyd_async.fastcs.panda import DatasetTable, PandaHdf5DatasetType
from ophyd_async.testing import callback_on_mock_put, set_mock_value
from PIL import Image
from pydantic.dataclasses import dataclass
from scanspec.core import Path as ScanPath
from scanspec.specs import Line

from mx_bluesky.common.external_interaction.callbacks.common.logging_callback import (
    VerbosePlanExecutionLoggingCallback,
)
from mx_bluesky.common.external_interaction.config_server import FeatureFlags
from mx_bluesky.common.parameters.constants import (
    DocDescriptorNames,
    EnvironmentConstants,
    PlanNameConstants,
)
from mx_bluesky.common.parameters.gridscan import SpecifiedThreeDGridScan
from mx_bluesky.common.utils.exceptions import CrystalNotFoundException
from mx_bluesky.common.utils.log import (
    ALL_LOGGERS,
    ISPYB_ZOCALO_CALLBACK_LOGGER,
    LOGGER,
    NEXUS_LOGGER,
    _get_logging_dirs,
    do_default_logging_setup,
)
from mx_bluesky.hyperion.experiment_plans.rotation_scan_plan import (
    RotationScanComposite,
)
from mx_bluesky.hyperion.parameters.device_composites import (
    HyperionFlyScanXRayCentreComposite,
)
from mx_bluesky.hyperion.parameters.gridscan import HyperionSpecifiedThreeDGridScan
from mx_bluesky.hyperion.parameters.rotation import MultiRotationScan

i03.DAQ_CONFIGURATION_PATH = "tests/test_data/test_daq_configuration"

TEST_GRAYLOG_PORT = 5555

TEST_RESULT_LARGE = [
    {
        "centre_of_mass": [1, 2, 3],
        "max_voxel": [1, 2, 3],
        "max_count": 105062,
        "n_voxels": 35,
        "total_count": 2387574,
        "bounding_box": [[2, 2, 2], [8, 8, 7]],
    }
]
TEST_RESULT_MEDIUM = [
    {
        "centre_of_mass": [1, 2, 3],
        "max_voxel": [2, 4, 5],
        "max_count": 50000,
        "n_voxels": 35,
        "total_count": 100000,
        "bounding_box": [[1, 2, 3], [3, 4, 4]],
    }
]
TEST_RESULT_SMALL = [
    {
        "centre_of_mass": [1, 2, 3],
        "max_voxel": [1, 2, 3],
        "max_count": 1000,
        "n_voxels": 35,
        "total_count": 1000,
        "bounding_box": [[2, 2, 2], [3, 3, 3]],
    }
]
TEST_RESULT_BELOW_THRESHOLD = [
    {
        "centre_of_mass": [2, 3, 4],
        "max_voxel": [2, 3, 4],
        "max_count": 2,
        "n_voxels": 1,
        "total_count": 2,
        "bounding_box": [[1, 2, 3], [2, 3, 4]],
    }
]

# These are the uncorrected coordinate from zocalo
TEST_RESULT_IN_BOUNDS_TOP_LEFT_BOX = [
    {
        "centre_of_mass": [0.5, 0.5, 0.5],
        "max_voxel": [0, 0, 0],
        "max_count": 50000,
        "n_voxels": 35,
        "total_count": 100000,
        "bounding_box": [[0, 0, 0], [3, 4, 4]],
    }
]
# These are the uncorrected coordinate from zocalo
TEST_RESULT_IN_BOUNDS_TOP_LEFT_GRID_CORNER = [
    {
        "centre_of_mass": [0.0, 0.0, 0.0],
        "max_voxel": [0, 0, 0],
        "max_count": 50000,
        "n_voxels": 35,
        "total_count": 100000,
        "bounding_box": [[0, 0, 0], [3, 4, 4]],
    }
]
# These are the uncorrected coordinate from zocalo
TEST_RESULT_OUT_OF_BOUNDS_COM = [
    {
        "centre_of_mass": [-0.0001, -0.0001, -0.0001],
        "max_voxel": [0, 0, 0],
        "max_count": 50000,
        "n_voxels": 35,
        "total_count": 100000,
        "bounding_box": [[0, 0, 0], [3, 4, 4]],
    }
]
# These are the uncorrected coordinate from zocalo
TEST_RESULT_OUT_OF_BOUNDS_BB = [
    {
        "centre_of_mass": [0, 0, 0],
        "max_voxel": [0, 0, 0],
        "max_count": 50000,
        "n_voxels": 35,
        "total_count": 100000,
        "bounding_box": [[-1, -1, -1], [3, 4, 4]],
    }
]


@dataclass(frozen=True)
class SimConstants:
    BEAMLINE = "BL03S"
    # The following are values present in the system test ispyb database
    ST_VISIT = "cm14451-2"
    ST_SAMPLE_ID = 398810
    ST_CONTAINER_ID = 34864


@pytest.fixture(autouse=True, scope="session")
def ispyb_config_path():
    ispyb_config_path = os.environ.get(
        "ISPYB_CONFIG_PATH", "tests/test_data/test_config.cfg"
    )
    with patch.dict(os.environ, {"ISPYB_CONFIG_PATH": ispyb_config_path}):
        yield ispyb_config_path


@pytest.fixture(scope="session")
def active_device_factories() -> set[AnyDeviceFactory]:
    """Obtain the set of device factories that should have their caches cleared
    after every test invocation.
    Override this in sub-packages for the specific beamlines under test."""
    return device_factories_for_beamline(i03)


def device_factories_for_beamline(beamline_module: ModuleType) -> set[AnyDeviceFactory]:
    return {
        f
        for f in collect_factories(beamline_module, include_skipped=True).values()
        if hasattr(f, "cache_clear")
    }


@pytest.fixture(scope="function", autouse=True)
def clear_device_factory_caches_after_every_test(active_device_factories):
    yield None
    for f in active_device_factories:
        f.cache_clear()  # type: ignore


def raw_params_from_file(filename):
    with open(filename) as f:
        return json.loads(f.read())


def default_raw_params(
    json_file="tests/test_data/parameter_json_files/good_test_parameters.json",
):
    return raw_params_from_file(json_file)


def create_dummy_scan_spec(x_steps, y_steps, z_steps):
    x_line = Line("sam_x", 0, 10, 10)
    y_line = Line("sam_y", 10, 20, 20)
    z_line = Line("sam_z", 30, 50, 30)

    specs = [y_line * ~x_line, z_line * ~x_line]
    specs = [ScanPath(spec.calculate()) for spec in specs]
    return [spec.consume().midpoints for spec in specs]


def _reset_loggers(loggers):
    """Clear all handlers and tear down the logging hierarchy, leave logger references intact."""
    clear_log_handlers(loggers)
    for logger in loggers:
        if logger.name != "Hyperion" and logger.name != "MX-Bluesky":
            # Hyperion parent is configured on module import, do not remove
            logger.parent = logging.getLogger()


def clear_log_handlers(loggers: Sequence[logging.Logger]):
    for logger in loggers:
        for handler in logger.handlers:
            handler.close()
        logger.handlers.clear()


def pytest_runtest_setup(item):
    markers = [m.name for m in item.own_markers]
    if item.config.getoption("logging") and "skip_log_setup" not in markers:
        if LOGGER.handlers == []:
            if dodal_logger.handlers == []:
                print("Initialising Hyperion logger for tests")
                do_default_logging_setup("dev_log.py", TEST_GRAYLOG_PORT, dev_mode=True)
        logging_path, _ = _get_logging_dirs()
        if ISPYB_ZOCALO_CALLBACK_LOGGER.handlers == []:
            print("Initialising ISPyB logger for tests")
            set_up_all_logging_handlers(
                ISPYB_ZOCALO_CALLBACK_LOGGER,
                logging_path,
                "hyperion_ispyb_callback.log",
                True,
                10000,
            )
        if NEXUS_LOGGER.handlers == []:
            print("Initialising nexus logger for tests")
            set_up_all_logging_handlers(
                NEXUS_LOGGER,
                logging_path,
                "hyperion_ispyb_callback.log",
                True,
                10000,
            )
    else:
        print("Skipping log setup for log test - deleting existing handlers")
        _reset_loggers([*ALL_LOGGERS, dodal_logger])


def pytest_runtest_teardown(item):
    if "dodal.common.beamlines.beamline_utils" in sys.modules:
        sys.modules["dodal.common.beamlines.beamline_utils"].clear_devices()
    markers = [m.name for m in item.own_markers]
    if "skip_log_setup" in markers:
        _reset_loggers([*ALL_LOGGERS, dodal_logger])


@pytest.fixture
def RE():
    RE = RunEngine({}, call_returns_result=True)
    RE.subscribe(
        VerbosePlanExecutionLoggingCallback()
    )  # log all events at INFO for easier debugging
    yield RE
    try:
        RE.halt()
    except Exception as e:
        print(f"Got exception while halting RunEngine {e}")
    finally:
        stopped_event = threading.Event()

        def stop_event_loop():
            RE.loop.stop()  # noqa: F821
            stopped_event.set()

        RE.loop.call_soon_threadsafe(stop_event_loop)
        stopped_event.wait(10)
    del RE


def pass_on_mock(motor: Motor, call_log: MagicMock | None = None):
    def _pass_on_mock(value: float, wait: bool):
        set_mock_value(motor.user_readback, value)
        if call_log is not None:
            call_log(value, wait=wait)

    return _pass_on_mock


def patch_async_motor(
    motor: Motor, initial_position=0, call_log: MagicMock | None = None
):
    set_mock_value(motor.user_setpoint, initial_position)
    set_mock_value(motor.user_readback, initial_position)
    set_mock_value(motor.deadband, 0.001)
    set_mock_value(motor.motor_done_move, 1)
    set_mock_value(motor.velocity, 1)
    return callback_on_mock_put(motor.user_setpoint, pass_on_mock(motor, call_log))


@pytest.fixture(params=[False, True])
def feature_flags_update_with_omega_flip(request):
    def update_with_overrides(self):
        self.overriden_features["omega_flip"] = request.param
        self.omega_flip = request.param

    with patch.object(FeatureFlags, "update_self_from_server", autospec=True) as update:
        update.side_effect = update_with_overrides
        yield update


@pytest.fixture
def beamline_parameters():
    return GDABeamlineParameters.from_file(
        "tests/test_data/test_beamline_parameters.txt"
    )


@pytest.fixture(autouse=True)
def i03_beamline_parameters():
    """Fix default i03 beamline parameters to refer to a test file not the /dls_sw folder"""
    with patch.dict(
        "dodal.common.beamlines.beamline_parameters.BEAMLINE_PARAMETER_PATHS",
        {"i03": "tests/test_data/test_beamline_parameters.txt"},
    ) as params:
        yield params


@pytest.fixture
def hyperion_fgs_params():
    return HyperionSpecifiedThreeDGridScan(
        **raw_params_from_file(
            "tests/test_data/parameter_json_files/good_test_parameters.json"
        )
    )


@pytest.fixture
def done_status():
    return NullStatus()


@pytest.fixture
def eiger(done_status, RE: RunEngine):
    eiger = i03.eiger(connect_immediately=True, mock=True)
    eiger.stage = MagicMock(return_value=done_status)
    eiger.do_arm.set = MagicMock(return_value=done_status)
    eiger.unstage = MagicMock(return_value=done_status)
    return eiger


@pytest.fixture
def smargon(RE: RunEngine) -> Generator[Smargon, None, None]:
    smargon = i03.smargon(connect_immediately=True, mock=True)
    # Initial positions, needed for stub_offsets
    set_mock_value(smargon.stub_offsets.center_at_current_position.disp, 0)
    set_mock_value(smargon.x.user_readback, 0.0)
    set_mock_value(smargon.y.user_readback, 0.0)
    set_mock_value(smargon.z.user_readback, 0.0)
    set_mock_value(smargon.x.high_limit_travel, 2)
    set_mock_value(smargon.x.low_limit_travel, -2)
    set_mock_value(smargon.y.high_limit_travel, 2)
    set_mock_value(smargon.y.low_limit_travel, -2)
    set_mock_value(smargon.z.high_limit_travel, 2)
    set_mock_value(smargon.z.low_limit_travel, -2)

    with (
        patch_async_motor(smargon.omega),
        patch_async_motor(smargon.x),
        patch_async_motor(smargon.y),
        patch_async_motor(smargon.z),
        patch_async_motor(smargon.chi),
        patch_async_motor(smargon.phi),
    ):
        yield smargon
    clear_devices()


@pytest.fixture
def zebra(RE: RunEngine):
    zebra = i03.zebra(connect_immediately=True, mock=True)

    def mock_side(demand: ArmDemand):
        set_mock_value(zebra.pc.arm.armed, demand.value)
        return NullStatus()

    zebra.pc.arm.set = MagicMock(side_effect=mock_side)
    return zebra


@pytest.fixture
def zebra_shutter(RE: RunEngine):
    return i03.sample_shutter(connect_immediately=True, mock=True)


@pytest.fixture
def backlight(RE: RunEngine):
    backlight = i03.backlight(connect_immediately=True, mock=True)
    backlight.TIME_TO_MOVE_S = 0.001
    return backlight


@pytest.fixture
def fast_grid_scan(RE: RunEngine):
    return i03.zebra_fast_grid_scan(connect_immediately=True, mock=True)


@pytest.fixture
def detector_motion(RE: RunEngine):
    det = i03.detector_motion(connect_immediately=True, mock=True)
    with patch_async_motor(det.z):
        yield det


@pytest.fixture
def undulator(RE: RunEngine):
    return i03.undulator(connect_immediately=True, mock=True)


@pytest.fixture
def s4_slit_gaps(RE: RunEngine):
    return i03.s4_slit_gaps(connect_immediately=True, mock=True)


@pytest.fixture
def synchrotron(RE: RunEngine):
    synchrotron = i03.synchrotron(connect_immediately=True, mock=True)
    set_mock_value(synchrotron.synchrotron_mode, SynchrotronMode.USER)
    set_mock_value(synchrotron.top_up_start_countdown, 10)
    return synchrotron


@pytest.fixture
def oav(test_config_files, RE: RunEngine):
    parameters = OAVConfig(
        test_config_files["zoom_params_file"], test_config_files["display_config"]
    )
    oav = i03.oav(connect_immediately=True, mock=True, params=parameters)

    zoom_levels_list = ["1.0x", "3.0x", "5.0x", "7.5x", "10.0x", "15.0x"]
    oav.zoom_controller._get_allowed_zoom_levels = AsyncMock(
        return_value=zoom_levels_list
    )
    # Equivalent to previously set values for microns and beam centre
    set_mock_value(oav.zoom_controller.level, "5.0x")

    set_mock_value(oav.grid_snapshot.x_size, 1024)
    set_mock_value(oav.grid_snapshot.y_size, 768)

    oav.snapshot.trigger = MagicMock(return_value=NullStatus())
    oav.grid_snapshot.trigger = MagicMock(return_value=NullStatus())
    yield oav


@pytest.fixture
def flux(RE: RunEngine):
    return i03.flux(connect_immediately=True, mock=True)


@pytest.fixture
def pin_tip(RE: RunEngine):
    return i03.pin_tip_detection(connect_immediately=True, mock=True)


@pytest.fixture
def ophyd_pin_tip_detection(RE: RunEngine):
    return i03.pin_tip_detection(connect_immediately=True, mock=True)


@pytest.fixture
def robot(done_status, RE: RunEngine):
    robot = i03.robot(connect_immediately=True, mock=True)
    set_mock_value(robot.barcode, "BARCODE")
    robot.set = MagicMock(return_value=done_status)
    return robot


@pytest.fixture
def attenuator(RE: RunEngine):
    attenuator = i03.attenuator(connect_immediately=True, mock=True)
    set_mock_value(attenuator.actual_transmission, 0.49118047952)

    @AsyncStatus.wrap
    async def fake_attenuator_set(val):
        set_mock_value(attenuator.actual_transmission, val)

    attenuator.set = MagicMock(side_effect=fake_attenuator_set)

    yield attenuator


@pytest.fixture
def beamstop_i03(
    beamline_parameters: GDABeamlineParameters,
    sim_run_engine: RunEngineSimulator,
    RE: RunEngine,
) -> Generator[Beamstop, Any, Any]:
    with patch(
        "dodal.beamlines.i03.get_beamline_parameters", return_value=beamline_parameters
    ):
        beamstop = i03.beamstop(connect_immediately=True, mock=True)
        patch_motor(beamstop.x_mm)
        patch_motor(beamstop.y_mm)
        patch_motor(beamstop.z_mm)
        set_mock_value(beamstop.x_mm.user_readback, 1.52)
        set_mock_value(beamstop.y_mm.user_readback, 44.78)
        set_mock_value(beamstop.z_mm.user_readback, 30.0)
        sim_run_engine.add_read_handler_for(
            beamstop.selected_pos, BeamstopPositions.DATA_COLLECTION
        )
        yield beamstop
        beamline_utils.clear_devices()


@pytest.fixture
def xbpm_feedback(done_status, RE: RunEngine):
    xbpm = i03.xbpm_feedback(connect_immediately=True, mock=True)
    xbpm.trigger = MagicMock(return_value=done_status)
    yield xbpm
    beamline_utils.clear_devices()


def set_up_dcm(dcm: DCM, sim_run_engine: RunEngineSimulator):
    set_mock_value(dcm.energy_in_kev.user_readback, 12.7)
    set_mock_value(dcm.xtal_1.pitch_in_mrad.user_readback, 1)
    set_mock_value(dcm.crystal_metadata_d_spacing_a, 3.13475)
    sim_run_engine.add_read_handler_for(dcm.crystal_metadata_d_spacing_a, 3.13475)
    patch_motor(dcm.xtal_1.roll_in_mrad)
    patch_motor(dcm.xtal_1.pitch_in_mrad)
    patch_motor(dcm.offset_in_mm)
    return dcm


@pytest.fixture
def dcm(RE: RunEngine, sim_run_engine):
    dcm = i03.dcm(connect_immediately=True, mock=True)
    set_up_dcm(dcm, sim_run_engine)
    yield dcm


@pytest.fixture
def vfm(RE: RunEngine):
    vfm = i03.vfm(connect_immediately=True, mock=True)
    vfm.bragg_to_lat_lookup_table_path = (
        "tests/test_data/test_beamline_vfm_lat_converter.txt"
    )
    with ExitStack() as stack:
        stack.enter_context(patch_motor(vfm.x_mm))
        yield vfm


@pytest.fixture
def lower_gonio(RE: RunEngine):
    lower_gonio = i03.lower_gonio(connect_immediately=True, mock=True)
    with (
        patch_motor(lower_gonio.x),
        patch_motor(lower_gonio.y),
        patch_motor(lower_gonio.z),
    ):
        yield lower_gonio


@pytest.fixture
def mirror_voltages(RE: RunEngine):
    voltages = i03.mirror_voltages(connect_immediately=True, mock=True)
    voltages.voltage_lookup_table_path = "tests/test_data/test_mirror_focus.json"
    for vc in voltages.vertical_voltages.values():
        vc.set = MagicMock(return_value=NullStatus())
    for vc in voltages.horizontal_voltages.values():
        vc.set = MagicMock(return_value=NullStatus())
    yield voltages
    beamline_utils.clear_devices()


@pytest.fixture
def undulator_dcm(RE: RunEngine, sim_run_engine, dcm):
    undulator_dcm = i03.undulator_dcm(
        connect_immediately=True,
        mock=True,
        daq_configuration_path="tests/test_data/test_daq_configuration",
    )
    set_up_dcm(undulator_dcm.dcm_ref(), sim_run_engine)  # type: ignore
    yield undulator_dcm
    beamline_utils.clear_devices()


@pytest.fixture
def webcam(RE: RunEngine) -> Generator[Webcam, Any, Any]:
    webcam = i03.webcam(connect_immediately=True, mock=True)
    with patch.object(webcam, "_get_and_write_image"):
        yield webcam


@pytest.fixture
def thawer(RE: RunEngine) -> Generator[Thawer, Any, Any]:
    yield i03.thawer(connect_immediately=True, mock=True)


@pytest.fixture
def sample_shutter(RE: RunEngine) -> Generator[ZebraShutter, Any, Any]:
    yield i03.sample_shutter(connect_immediately=True, mock=True)


@pytest.fixture
async def aperture_scatterguard(RE: RunEngine):
    positions = {
        ApertureValue.LARGE: AperturePosition(
            aperture_x=0,
            aperture_y=1,
            aperture_z=2,
            scatterguard_x=3,
            scatterguard_y=4,
            radius=100,
        ),
        ApertureValue.MEDIUM: AperturePosition(
            aperture_x=5,
            aperture_y=6,
            aperture_z=2,
            scatterguard_x=8,
            scatterguard_y=9,
            radius=50,
        ),
        ApertureValue.SMALL: AperturePosition(
            aperture_x=10,
            aperture_y=11,
            aperture_z=2,
            scatterguard_x=13,
            scatterguard_y=14,
            radius=20,
        ),
        ApertureValue.OUT_OF_BEAM: AperturePosition(
            aperture_x=15,
            aperture_y=16,
            aperture_z=2,
            scatterguard_x=18,
            scatterguard_y=19,
            radius=0,
        ),
    }
    with (
        patch(
            "dodal.beamlines.i03.load_positions_from_beamline_parameters",
            return_value=positions,
        ),
        patch(
            "dodal.beamlines.i03.AperturePosition.tolerances_from_gda_params",
            return_value=AperturePosition(
                aperture_x=0.1,
                aperture_y=0.1,
                aperture_z=0.1,
                scatterguard_x=0.1,
                scatterguard_y=0.1,
            ),
        ),
    ):
        ap_sg = i03.aperture_scatterguard(connect_immediately=True, mock=True)
    with (
        patch_async_motor(ap_sg.aperture.x),
        patch_async_motor(ap_sg.aperture.y),
        patch_async_motor(ap_sg.aperture.z, 2),
        patch_async_motor(ap_sg.scatterguard.x),
        patch_async_motor(ap_sg.scatterguard.y),
    ):
        await ap_sg.selected_aperture.set(ApertureValue.SMALL)

        set_mock_value(ap_sg.aperture.small, 1)
        yield ap_sg


@pytest.fixture()
def test_config_files():
    return {
        "zoom_params_file": "tests/test_data/test_jCameraManZoomLevels.xml",
        "oav_config_json": "tests/test_data/test_OAVCentring.json",
        "display_config": "tests/test_data/test_display.configuration",
    }


@pytest.fixture()
def fake_create_devices(
    beamstop_i03: Beamstop,
    eiger: EigerDetector,
    smargon: Smargon,
    zebra: Zebra,
    detector_motion: DetectorMotion,
    aperture_scatterguard: ApertureScatterguard,
    backlight: Backlight,
):
    mock_omega_sets = MagicMock(return_value=NullStatus())

    smargon.omega.velocity.set = mock_omega_sets
    smargon.omega.set = mock_omega_sets

    devices = {
        "beamstop": beamstop_i03,
        "eiger": eiger,
        "smargon": smargon,
        "zebra": zebra,
        "detector_motion": detector_motion,
        "backlight": backlight,
        "ap_sg": aperture_scatterguard,
    }
    return devices


@pytest.fixture()
def fake_create_rotation_devices(
    beamstop_i03: Beamstop,
    eiger: EigerDetector,
    smargon: Smargon,
    zebra: Zebra,
    detector_motion: DetectorMotion,
    backlight: Backlight,
    attenuator: BinaryFilterAttenuator,
    flux: Flux,
    undulator: Undulator,
    aperture_scatterguard: ApertureScatterguard,
    synchrotron: Synchrotron,
    s4_slit_gaps: S4SlitGaps,
    dcm: DCM,
    robot: BartRobot,
    oav: OAV,
    sample_shutter: ZebraShutter,
    xbpm_feedback: XBPMFeedback,
):
    set_mock_value(smargon.omega.max_velocity, 131)
    undulator.set = MagicMock(return_value=NullStatus())
    return RotationScanComposite(
        attenuator=attenuator,
        backlight=backlight,
        beamstop=beamstop_i03,
        dcm=dcm,
        detector_motion=detector_motion,
        eiger=eiger,
        flux=flux,
        smargon=smargon,
        undulator=undulator,
        aperture_scatterguard=aperture_scatterguard,
        synchrotron=synchrotron,
        s4_slit_gaps=s4_slit_gaps,
        zebra=zebra,
        robot=robot,
        oav=oav,
        sample_shutter=sample_shutter,
        xbpm_feedback=xbpm_feedback,
    )


@pytest.fixture
def zocalo(done_status, RE: RunEngine):
    zoc = i03.zocalo(connect_immediately=True, mock=True)
    zoc.stage = MagicMock(return_value=done_status)
    zoc.unstage = MagicMock(return_value=done_status)
    return zoc


@pytest.fixture
async def panda(RE: RunEngine):
    class MockBlock(Device):
        def __init__(
            self,
            prefix: str,
            name: str = "",
            attributes: dict[str, Any] = {},  # noqa
        ):
            for name, dtype in attributes.items():
                setattr(self, name, epics_signal_rw(dtype, "", ""))
            super().__init__(name)

    def mock_vector_block(n, attributes):
        return DeviceVector(
            {i: MockBlock(f"{i}", f"{i}", attributes) for i in range(n)}
        )

    async def set_mock_blocks(
        panda, mock_blocks: dict[str, tuple[int, dict[str, Any]]]
    ):
        for name, block in mock_blocks.items():
            n, attrs = block
            block = mock_vector_block(n, attrs)
            await block.connect(mock=True)
            setattr(panda, name, block)

    async def create_mock_signals(devices_and_signals: dict[Device, dict[str, Any]]):
        for device, signals in devices_and_signals.items():
            for name, dtype in signals.items():
                sig = epics_signal_rw(dtype, name, name)
                await sig.connect(mock=True)
                setattr(device, name, sig)

    panda = i03.panda(connect_immediately=True, mock=True)
    await set_mock_blocks(
        panda,
        {
            "inenc": (8, {"setp": float}),
            "clock": (8, {"period": float}),
            "counter": (8, {"enable": str}),
        },
    )
    await create_mock_signals(
        {
            panda.pcap: {"enable": str},
            **{panda.pulse[i]: {"enable": str} for i in panda.pulse.keys()},
        }
    )

    set_mock_value(
        panda.data.datasets,
        DatasetTable(name=["name"], dtype=[PandaHdf5DatasetType.FLOAT_64]),
    )

    return panda


@pytest.fixture
def oav_parameters_for_rotation(test_config_files) -> OAVParameters:
    return OAVParameters(oav_config_json=test_config_files["oav_config_json"])


async def async_status_done():
    await asyncio.sleep(0)


def mock_gridscan_kickoff_complete(gridscan: FastGridScanCommon):
    gridscan.kickoff = MagicMock(return_value=async_status_done)
    gridscan.complete = MagicMock(return_value=async_status_done)


@pytest.fixture
def panda_fast_grid_scan(RE: RunEngine):
    return i03.panda_fast_grid_scan(connect_immediately=True, mock=True)


@pytest.fixture
async def hyperion_flyscan_xrc_composite(
    smargon: Smargon,
    hyperion_fgs_params: HyperionSpecifiedThreeDGridScan,
    RE: RunEngine,
    done_status,
    attenuator,
    xbpm_feedback,
    synchrotron,
    aperture_scatterguard,
    zocalo,
    dcm,
    panda,
    backlight,
    s4_slit_gaps,
) -> HyperionFlyScanXRayCentreComposite:
    fake_composite = HyperionFlyScanXRayCentreComposite(
        aperture_scatterguard=aperture_scatterguard,
        attenuator=attenuator,
        backlight=backlight,
        dcm=dcm,
        # We don't use the eiger fixture here because .unstage() is used in some tests
        eiger=i03.eiger(connect_immediately=True, mock=True),
        zebra_fast_grid_scan=i03.zebra_fast_grid_scan(
            connect_immediately=True, mock=True
        ),
        flux=i03.flux(connect_immediately=True, mock=True),
        s4_slit_gaps=s4_slit_gaps,
        smargon=smargon,
        undulator=i03.undulator(connect_immediately=True, mock=True),
        synchrotron=synchrotron,
        xbpm_feedback=xbpm_feedback,
        zebra=i03.zebra(connect_immediately=True, mock=True),
        zocalo=zocalo,
        panda=panda,
        panda_fast_grid_scan=i03.panda_fast_grid_scan(
            connect_immediately=True, mock=True
        ),
        robot=i03.robot(connect_immediately=True, mock=True),
        sample_shutter=i03.sample_shutter(connect_immediately=True, mock=True),
    )

    fake_composite.eiger.stage = MagicMock(return_value=done_status)
    # unstage should be mocked on a per-test basis because several rely on unstage
    fake_composite.eiger.set_detector_parameters(hyperion_fgs_params.detector_params)
    fake_composite.eiger.stop_odin_when_all_frames_collected = MagicMock()
    fake_composite.eiger.odin.check_and_wait_for_odin_state = lambda timeout: True

    test_result = {
        "centre_of_mass": [6, 6, 6],
        "max_voxel": [5, 5, 5],
        "max_count": 123456,
        "n_voxels": 321,
        "total_count": 999999,
        "bounding_box": [[3, 3, 3], [9, 9, 9]],
    }

    @AsyncStatus.wrap
    async def mock_complete(result):
        await fake_composite.zocalo._put_results([result], {"dcid": 0, "dcgid": 0})

    fake_composite.zocalo.trigger = MagicMock(
        side_effect=partial(mock_complete, test_result)
    )  # type: ignore
    fake_composite.zocalo.timeout_s = 3
    set_mock_value(fake_composite.zebra_fast_grid_scan.scan_invalid, False)
    set_mock_value(fake_composite.zebra_fast_grid_scan.position_counter, 0)
    set_mock_value(fake_composite.smargon.x.max_velocity, 10)

    set_mock_value(fake_composite.robot.barcode, "BARCODE")

    return fake_composite


def fake_read(obj, initial_positions, _):
    initial_positions[obj] = 0
    yield Msg("null", obj)


def extract_metafile(input_filename, output_filename):
    with gzip.open(input_filename) as metafile_fo:
        with open(output_filename, "wb") as output_fo:
            output_fo.write(metafile_fo.read())


@pytest.fixture
def sim_run_engine():
    return RunEngineSimulator()


class DocumentCapturer:
    """A utility which can be subscribed to the RunEngine in place of a callback in order
    to intercept documents and make assertions about their contents"""

    def __init__(self) -> None:
        self.docs_received: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.docs_received.append((args[0], args[1]))

    @staticmethod
    def is_match(
        doc: tuple[str, dict[str, Any]],
        name: str,
        has_fields: Sequence[str] = [],
        matches_fields: dict[str, Any] = {},  # noqa
    ):
        """Returns True if the given document:
        - has the same name
        - contains all the fields in has_fields
        - contains all the fields in matches_fields with the same content"""

        return (
            doc[0] == name
            and all(f in doc[1].keys() for f in has_fields)
            and matches_fields.items() <= doc[1].items()
        )

    @staticmethod
    def get_matches(
        docs: list[tuple[str, dict[str, Any]]],
        name: str,
        has_fields: Sequence[str] = [],
        matches_fields: dict[str, Any] = {},  # noqa
    ):
        """Get all the docs from docs which:
        - have the same name
        - contain all the fields in has_fields
        - contain all the fields in matches_fields with the same content"""
        return list(
            filter(
                partial(
                    DocumentCapturer.is_match,
                    name=name,
                    has_fields=has_fields,
                    matches_fields=matches_fields,
                ),
                docs,
            )
        )

    @staticmethod
    def assert_doc(
        docs: list[tuple[str, dict[str, Any]]],
        name: str,
        has_fields: Sequence[str] = [],
        matches_fields: dict[str, Any] = {},  # noqa
        does_exist: bool = True,
    ):
        """Assert that a matching doc has been received by the sim,
        and returns the first match if it is meant to exist"""
        matches = DocumentCapturer.get_matches(docs, name, has_fields, matches_fields)
        if does_exist:
            assert matches
            return matches[0]
        else:
            assert matches == []

    @staticmethod
    def get_docs_until(
        docs: list[tuple[str, dict[str, Any]]],
        name: str,
        has_fields: Sequence[str] = [],
        matches_fields: dict[str, Any] = {},  # noqa
    ):
        """return all the docs from the list of docs until the first matching one"""
        for i, doc in enumerate(docs):
            if DocumentCapturer.is_match(doc, name, has_fields, matches_fields):
                return docs[: i + 1]
        raise ValueError(f"Doc {name=}, {has_fields=}, {matches_fields=} not found")

    @staticmethod
    def get_docs_from(
        docs: list[tuple[str, dict[str, Any]]],
        name: str,
        has_fields: Sequence[str] = [],
        matches_fields: dict[str, Any] = {},  # noqa
    ):
        """return all the docs from the list of docs after the first matching one"""
        for i, doc in enumerate(docs):
            if DocumentCapturer.is_match(doc, name, has_fields, matches_fields):
                return docs[i:]
        raise ValueError(f"Doc {name=}, {has_fields=}, {matches_fields=} not found")

    @staticmethod
    def assert_events_and_data_in_order(
        docs: list[tuple[str, dict[str, Any]]],
        match_data_keys_list: Sequence[Sequence[str]],
    ):
        for event_data_keys in match_data_keys_list:
            docs = DocumentCapturer.get_docs_from(docs, "event")
            doc = docs.pop(0)[1]["data"]
            assert all(k in doc.keys() for k in event_data_keys), (
                f"One of {event_data_keys=} not in {doc}"
            )


def assert_none_matching(
    messages: list[Msg],
    predicate: Callable[[Msg], bool],
):
    assert not list(filter(predicate, messages))


def pin_tip_edge_data():
    tip_x_px = 130
    tip_y_px = 200
    microns_per_pixel = 2.87  # from zoom levels .xml
    grid_width_px = int(400 / microns_per_pixel)
    target_grid_height_px = 140
    top_edge_data = ([0] * tip_x_px) + (
        [(tip_y_px - target_grid_height_px // 2)] * grid_width_px
    )
    bottom_edge_data = [0] * tip_x_px + [
        (tip_y_px + target_grid_height_px // 2)
    ] * grid_width_px
    top_edge_array = numpy.array(top_edge_data, dtype=numpy.uint32)
    bottom_edge_array = numpy.array(bottom_edge_data, dtype=numpy.uint32)
    return tip_x_px, tip_y_px, top_edge_array, bottom_edge_array


def find_a_pin(pin_tip_detection):
    def set_good_position():
        x, y, top_edge_array, bottom_edge_array = pin_tip_edge_data()
        set_mock_value(pin_tip_detection.triggered_tip, numpy.array([x, y]))
        set_mock_value(pin_tip_detection.triggered_top_edge, top_edge_array)
        set_mock_value(pin_tip_detection.triggered_bottom_edge, bottom_edge_array)
        return NullStatus()

    return set_good_position


@pytest.fixture
def pin_tip_detection_with_found_pin(ophyd_pin_tip_detection: PinTipDetection):
    with patch.object(
        ophyd_pin_tip_detection,
        "trigger",
        side_effect=find_a_pin(ophyd_pin_tip_detection),
    ):
        yield ophyd_pin_tip_detection


# Prevent pytest from catching exceptions when debugging in vscode so that break on
# exception works correctly (see: https://github.com/pytest-dev/pytest/issues/7409)
if os.getenv("PYTEST_RAISE", "0") == "1":

    @pytest.hookimpl(tryfirst=True)
    def pytest_exception_interact(call: pytest.CallInfo[Any]):
        if call.excinfo is not None:
            raise call.excinfo.value
        else:
            raise RuntimeError(
                f"{call} has no exception data, an unknown error has occurred"
            )

    @pytest.hookimpl(tryfirst=True)
    def pytest_internalerror(excinfo: pytest.ExceptionInfo[Any]):
        raise excinfo.value


def simulate_xrc_result(
    sim_run_engine: RunEngineSimulator,
    zocalo: ZocaloResults,
    test_results: Sequence[dict],
):
    for k in test_results[0].keys():
        sim_run_engine.add_read_handler_for(
            getattr(zocalo, k), numpy.array([r[k] for r in test_results])
        )


# The remaining code in this conftest is utility for external interaction tests. See https://github.com/DiamondLightSource/mx-bluesky/issues/699 for
# a better organisation of this


def default_raw_gridscan_params(
    json_file="tests/test_data/parameter_json_files/test_gridscan_param_defaults.json",
):
    return raw_params_from_file(json_file)


def dummy_params():
    dummy_params = SpecifiedThreeDGridScan(**default_raw_gridscan_params())
    return dummy_params


def dummy_params_2d():
    raw_params = raw_params_from_file(
        "tests/test_data/parameter_json_files/test_gridscan_param_defaults.json"
    )
    raw_params["z_steps"] = 1
    return SpecifiedThreeDGridScan(**raw_params)


TEST_SESSION_ID = 90
EXPECTED_START_TIME = "2024-02-08 14:03:59"
EXPECTED_END_TIME = "2024-02-08 14:04:01"
TEST_DATA_COLLECTION_IDS = (12, 13)
TEST_DATA_COLLECTION_GROUP_ID = 34
TEST_POSITION_ID = 78
TEST_GRID_INFO_IDS = (56, 57)
TEST_SAMPLE_ID = 364758
TEST_BARCODE = "12345A"


def mx_acquisition_from_conn(mock_ispyb_conn) -> MagicMock:
    return mock_ispyb_conn.return_value.__enter__.return_value.mx_acquisition


def assert_upsert_call_with(call, param_template, expected: dict):
    actual = remap_upsert_columns(list(param_template), call.args[0])
    assert actual == dict(param_template | expected)


def remap_upsert_columns(keys: Sequence[str], values: list):
    return dict(zip(keys, values, strict=False))


class OavGridSnapshotTestEvents:
    test_descriptor_document_oav_snapshot: EventDescriptor = {
        "uid": "b5ba4aec-de49-4970-81a4-b4a847391d34",
        "run_start": "d8bee3ee-f614-4e7a-a516-25d6b9e87ef3",
        "name": DocDescriptorNames.OAV_GRID_SNAPSHOT_TRIGGERED,
    }  # type: ignore
    test_event_document_oav_snapshot_xy: Event = {
        "descriptor": "b5ba4aec-de49-4970-81a4-b4a847391d34",
        "time": 1666604299.828203,
        "timestamps": {},
        "seq_num": 1,
        "uid": "29033ecf-e052-43dd-98af-c7cdd62e8174",
        "data": {
            "oav-grid_snapshot-top_left_x": 50,
            "oav-grid_snapshot-top_left_y": 100,
            "oav-grid_snapshot-num_boxes_x": 40,
            "oav-grid_snapshot-num_boxes_y": 20,
            "oav-microns_per_pixel_x": 1.58,
            "oav-microns_per_pixel_y": 1.58,
            "oav-beam_centre_i": 517,
            "oav-beam_centre_j": 350,
            "oav-grid_snapshot-box_width": 0.1 * 1000 / 1.25,  # size in pixels
            "oav-grid_snapshot-last_path_full_overlay": "test_1_y",
            "oav-grid_snapshot-last_path_outer": "test_2_y",
            "oav-grid_snapshot-last_saved_path": "test_3_y",
            "smargon-omega": 0,
            "smargon-x": 0,
            "smargon-y": 0,
            "smargon-z": 0,
        },
    }
    test_event_document_oav_snapshot_xz: Event = {
        "descriptor": "b5ba4aec-de49-4970-81a4-b4a847391d34",
        "time": 1666604299.828203,
        "timestamps": {},
        "seq_num": 1,
        "uid": "29033ecf-e052-43dd-98af-c7cdd62e8174",
        "data": {
            "oav-grid_snapshot-top_left_x": 50,
            "oav-grid_snapshot-top_left_y": 0,
            "oav-grid_snapshot-num_boxes_x": 40,
            "oav-grid_snapshot-num_boxes_y": 10,
            "oav-grid_snapshot-box_width": 0.1 * 1000 / 1.25,  # size in pixels
            "oav-grid_snapshot-last_path_full_overlay": "test_1_z",
            "oav-grid_snapshot-last_path_outer": "test_2_z",
            "oav-grid_snapshot-last_saved_path": "test_3_z",
            "oav-microns_per_pixel_x": 1.58,
            "oav-microns_per_pixel_y": 1.58,
            "oav-beam_centre_i": 517,
            "oav-beam_centre_j": 350,
            "smargon-omega": -90,
            "smargon-x": 0,
            "smargon-y": 0,
            "smargon-z": 0,
        },
    }


class TestData(OavGridSnapshotTestEvents):
    DUMMY_TIME_STRING: str = "1970-01-01 00:00:00"
    GOOD_ISPYB_RUN_STATUS: str = "DataCollection Successful"
    BAD_ISPYB_RUN_STATUS: str = "DataCollection Unsuccessful"
    test_start_document: RunStart = {  # type: ignore
        "uid": "d8bee3ee-f614-4e7a-a516-25d6b9e87ef3",
        "time": 1666604299.6149616,
        "versions": {"ophyd": "1.6.4.post76+g0895f9f", "bluesky": "1.8.3"},
        "scan_id": 1,
        "plan_type": "generator",
        "plan_name": PlanNameConstants.GRIDSCAN_OUTER,
        "subplan_name": PlanNameConstants.GRIDSCAN_OUTER,
        "mx_bluesky_parameters": dummy_params().model_dump_json(),
    }
    test_gridscan3d_start_document: RunStart = {  # type: ignore
        "uid": "d8bee3ee-f614-4e7a-a516-25d6b9e87ef3",
        "time": 1666604299.6149616,
        "versions": {"ophyd": "1.6.4.post76+g0895f9f", "bluesky": "1.8.3"},
        "scan_id": 1,
        "plan_type": "generator",
        "plan_name": "test",
        "subplan_name": PlanNameConstants.GRID_DETECT_AND_DO_GRIDSCAN,
        "mx_bluesky_parameters": dummy_params().model_dump_json(),
    }
    test_gridscan3d_stop_document_with_crystal_exception: RunStop = {
        "run_start": "d8bee3ee-f614-4e7a-a516-25d6b9e87ef3",
        "time": 1666604299.6149616,
        "uid": "65b2bde5-5740-42d7-9047-e860e06fbe15",
        "exit_status": "fail",
        "reason": f"{CrystalNotFoundException()}",
    }
    test_gridscan2d_start_document = {
        "uid": "d8bee3ee-f614-4e7a-a516-25d6b9e87ef3",
        "time": 1666604299.6149616,
        "versions": {"ophyd": "1.6.4.post76+g0895f9f", "bluesky": "1.8.3"},
        "scan_id": 1,
        "plan_type": "generator",
        "plan_name": "test",
        "subplan_name": PlanNameConstants.GRID_DETECT_AND_DO_GRIDSCAN,
        "mx_bluesky_parameters": dummy_params_2d().model_dump_json(),
    }
    test_rotation_start_main_document = {
        "uid": "2093c941-ded1-42c4-ab74-ea99980fbbfd",
        "subplan_name": PlanNameConstants.ROTATION_MAIN,
        "zocalo_environment": EnvironmentConstants.ZOCALO_ENV,
    }
    test_gridscan_outer_start_document = {
        "uid": "d8bee3ee-f614-4e7a-a516-25d6b9e87ef3",
        "time": 1666604299.6149616,
        "versions": {"ophyd": "1.6.4.post76+g0895f9f", "bluesky": "1.8.3"},
        "scan_id": 1,
        "plan_type": "generator",
        "plan_name": PlanNameConstants.GRIDSCAN_OUTER,
        "subplan_name": PlanNameConstants.GRIDSCAN_OUTER,
        "zocalo_environment": EnvironmentConstants.ZOCALO_ENV,
        "mx_bluesky_parameters": dummy_params().model_dump_json(),
    }
    test_rotation_event_document_during_data_collection: Event = {
        "descriptor": "bd45c2e5-2b85-4280-95d7-a9a15800a78b",
        "time": 2666604299.928203,
        "data": {
            "aperture_scatterguard-aperture-x": 15,
            "aperture_scatterguard-aperture-y": 16,
            "aperture_scatterguard-aperture-z": 2,
            "aperture_scatterguard-scatterguard-x": 18,
            "aperture_scatterguard-scatterguard-y": 19,
            "aperture_scatterguard-selected_aperture": ApertureValue.MEDIUM,
            "aperture_scatterguard-radius": 50,
            "attenuator-actual_transmission": 0.98,
            "flux-flux_reading": 9.81,
            "dcm-energy_in_kev": 11.105,
        },
        "timestamps": {"det1": 1666604299.8220396, "det2": 1666604299.8235943},
        "seq_num": 1,
        "uid": "2093c941-ded1-42c4-ab74-ea99980fbbfd",
        "filled": {},
    }
    test_rotation_stop_main_document: RunStop = {
        "run_start": "2093c941-ded1-42c4-ab74-ea99980fbbfd",
        "time": 1666604300.0310638,
        "uid": "65b2bde5-5740-42d7-9047-e860e06fbe15",
        "exit_status": "success",
        "reason": "Test succeeded",
        "num_events": {"fake_ispyb_params": 1, "primary": 1},
    }
    test_run_gridscan_start_document: RunStart = {  # type: ignore
        "uid": "d8bee3ee-f614-4e7a-a516-25d6b9e87ef3",
        "time": 1666604299.6149616,
        "versions": {"ophyd": "1.6.4.post76+g0895f9f", "bluesky": "1.8.3"},
        "scan_id": 1,
        "plan_type": "generator",
        "plan_name": PlanNameConstants.GRIDSCAN_AND_MOVE,
        "subplan_name": PlanNameConstants.GRIDSCAN_MAIN,
    }
    test_do_fgs_start_document: RunStart = {  # type: ignore
        "uid": "d8bee3ee-f614-4e7a-a516-25d6b9e87ef3",
        "time": 1666604299.6149616,
        "versions": {"ophyd": "1.6.4.post76+g0895f9f", "bluesky": "1.8.3"},
        "scan_id": 1,
        "plan_type": "generator",
        "plan_name": PlanNameConstants.GRIDSCAN_AND_MOVE,
        "subplan_name": PlanNameConstants.DO_FGS,
        "scan_points": create_dummy_scan_spec(10, 20, 30),
    }
    test_descriptor_document_oav_rotation_snapshot: EventDescriptor = {
        "uid": "c7d698ce-6d49-4c56-967e-7d081f964573",
        "run_start": "d8bee3ee-f614-4e7a-a516-25d6b9e87ef3",
        "name": DocDescriptorNames.OAV_ROTATION_SNAPSHOT_TRIGGERED,
    }  # type: ignore
    test_descriptor_document_pre_data_collection: EventDescriptor = {
        "uid": "bd45c2e5-2b85-4280-95d7-a9a15800a78b",
        "run_start": "d8bee3ee-f614-4e7a-a516-25d6b9e87ef3",
        "name": DocDescriptorNames.HARDWARE_READ_PRE,
    }  # type: ignore
    test_descriptor_document_during_data_collection: EventDescriptor = {
        "uid": "bd45c2e5-2b85-4280-95d7-a9a15800a78b",
        "run_start": "d8bee3ee-f614-4e7a-a516-25d6b9e87ef3",
        "name": DocDescriptorNames.HARDWARE_READ_DURING,
    }  # type: ignore
    test_descriptor_document_zocalo_hardware: EventDescriptor = {
        "uid": "f082901b-7453-4150-8ae5-c5f98bb34406",
        "run_start": "d8bee3ee-f614-4e7a-a516-25d6b9e87ef3",
        "name": DocDescriptorNames.ZOCALO_HW_READ,
    }  # type: ignore
    test_event_document_oav_rotation_snapshot: Event = {
        "descriptor": "c7d698ce-6d49-4c56-967e-7d081f964573",
        "time": 1666604299.828203,
        "timestamps": {},
        "seq_num": 1,
        "uid": "32d7c25c-c310-4292-ac78-36ce6509be3d",
        "data": {"oav-snapshot-last_saved_path": "snapshot_0"},
    }
    test_event_document_pre_data_collection: Event = {
        "descriptor": "bd45c2e5-2b85-4280-95d7-a9a15800a78b",
        "time": 1666604299.828203,
        "data": {
            "s4_slit_gaps-xgap": 0.1234,
            "s4_slit_gaps-ygap": 0.2345,
            "synchrotron-synchrotron_mode": SynchrotronMode.USER,
            "undulator-current_gap": 1.234,
            "smargon-x": 0.158435435,
            "smargon-y": 0.023547354,
            "smargon-z": 0.00345684712,
            "dcm-energy_in_kev": 11.105,
        },
        "timestamps": {"det1": 1666604299.8220396, "det2": 1666604299.8235943},
        "seq_num": 1,
        "uid": "29033ecf-e052-43dd-98af-c7cdd62e8173",
        "filled": {},
    }
    test_event_document_during_data_collection: Event = {
        "descriptor": "bd45c2e5-2b85-4280-95d7-a9a15800a78b",
        "time": 2666604299.928203,
        "data": {
            "aperture_scatterguard-aperture-x": 15,
            "aperture_scatterguard-aperture-y": 16,
            "aperture_scatterguard-aperture-z": 2,
            "aperture_scatterguard-scatterguard-x": 18,
            "aperture_scatterguard-scatterguard-y": 19,
            "aperture_scatterguard-selected_aperture": ApertureValue.MEDIUM,
            "aperture_scatterguard-radius": 50,
            "attenuator-actual_transmission": 1,
            "flux-flux_reading": 10,
            "dcm-energy_in_kev": 11.105,
            "eiger_bit_depth": "16",
        },
        "timestamps": {
            "det1": 1666604299.8220396,
            "det2": 1666604299.8235943,
            "eiger_bit_depth": 1666604299.8220396,
        },
        "seq_num": 1,
        "uid": "29033ecf-e052-43dd-98af-c7cdd62e8174",
        "filled": {},
    }
    test_event_document_zocalo_hardware: Event = {
        "uid": "29033ecf-e052-43dd-98af-c7cdd62e8175",
        "time": 1709654583.9770422,
        "data": {"eiger_odin_file_writer_id": "test_path"},
        "timestamps": {"eiger_odin_file_writer_id": 1666604299.8220396},
        "seq_num": 1,
        "filled": {},
        "descriptor": "f082901b-7453-4150-8ae5-c5f98bb34406",
    }
    test_stop_document: RunStop = {
        "run_start": "d8bee3ee-f614-4e7a-a516-25d6b9e87ef3",
        "time": 1666604300.0310638,
        "uid": "65b2bde5-5740-42d7-9047-e860e06fbe15",
        "exit_status": "success",
        "reason": "",
        "num_events": {"fake_ispyb_params": 1, "primary": 1},
    }
    test_run_gridscan_stop_document: RunStop = {
        "run_start": "d8bee3ee-f614-4e7a-a516-25d6b9e87ef3",
        "time": 1666604300.0310638,
        "uid": "65b2bde5-5740-42d7-9047-e860e06fbe15",
        "exit_status": "success",
        "reason": "",
        "num_events": {"fake_ispyb_params": 1, "primary": 1},
    }
    test_do_fgs_gridscan_stop_document: RunStop = {
        "run_start": "d8bee3ee-f614-4e7a-a516-25d6b9e87ef3",
        "time": 1666604300.0310638,
        "uid": "65b2bde5-5740-42d7-9047-e860e06fbe15",
        "exit_status": "success",
        "reason": "",
        "num_events": {"fake_ispyb_params": 1, "primary": 1},
    }
    test_failed_stop_document: RunStop = {
        "run_start": "d8bee3ee-f614-4e7a-a516-25d6b9e87ef3",
        "time": 1666604300.0310638,
        "uid": "65b2bde5-5740-42d7-9047-e860e06fbe15",
        "exit_status": "fail",
        "reason": "could not connect to devices",
        "num_events": {"fake_ispyb_params": 1, "primary": 1},
    }
    test_run_gridscan_failed_stop_document: RunStop = {
        "run_start": "d8bee3ee-f614-4e7a-a516-25d6b9e87ef3",
        "time": 1666604300.0310638,
        "uid": "65b2bde5-5740-42d7-9047-e860e06fbe15",
        "exit_status": "fail",
        "reason": "could not connect to devices",
        "num_events": {"fake_ispyb_params": 1, "primary": 1},
    }

    test_result_large = [
        {
            "centre_of_mass": [1, 2, 3],
            "max_voxel": [1, 2, 3],
            "max_count": 105062,
            "n_voxels": 35,
            "total_count": 2387574,
            "bounding_box": [[2, 2, 2], [8, 8, 7]],
        }
    ]
    test_result_medium = [
        {
            "centre_of_mass": [1, 2, 3],
            "max_voxel": [2, 4, 5],
            "max_count": 50000,
            "n_voxels": 35,
            "total_count": 100000,
            "bounding_box": [[1, 2, 3], [3, 4, 4]],
        }
    ]
    test_result_small = [
        {
            "centre_of_mass": [1, 2, 3],
            "max_voxel": [1, 2, 3],
            "max_count": 1000,
            "n_voxels": 35,
            "total_count": 1000,
            "bounding_box": [[2, 2, 2], [3, 3, 3]],
        }
    ]
    test_result_below_threshold = [
        {
            "centre_of_mass": [2, 3, 4],
            "max_voxel": [2, 3, 4],
            "max_count": 2,
            "n_voxels": 1,
            "total_count": 2,
            "bounding_box": [[1, 2, 3], [2, 3, 4]],
        }
    ]


def _mock_ispyb_conn(base_ispyb_conn, position_id, dcgid, dcids, giids):
    def upsert_data_collection(values):
        kvpairs = remap_upsert_columns(
            list(MXAcquisition.get_data_collection_params()), values
        )
        if kvpairs["id"]:
            return kvpairs["id"]
        else:
            return next(upsert_data_collection.i)  # pyright: ignore

    mx_acq = base_ispyb_conn.return_value.mx_acquisition
    mx_acq.upsert_data_collection.side_effect = upsert_data_collection
    mx_acq.update_dc_position.return_value = position_id
    mx_acq.upsert_data_collection_group.return_value = dcgid

    def upsert_dc_grid(values):
        kvpairs = remap_upsert_columns(list(MXAcquisition.get_dc_grid_params()), values)
        if kvpairs["id"]:
            return kvpairs["id"]
        else:
            return next(upsert_dc_grid.i)  # pyright: ignore

    upsert_data_collection.i = iter(dcids)  # pyright: ignore
    upsert_dc_grid.i = iter(giids)  # pyright: ignore

    mx_acq.upsert_dc_grid.side_effect = upsert_dc_grid
    return base_ispyb_conn


@pytest.fixture
def mock_ispyb_conn(base_ispyb_conn):
    return _mock_ispyb_conn(
        base_ispyb_conn,
        TEST_POSITION_ID,
        TEST_DATA_COLLECTION_GROUP_ID,
        TEST_DATA_COLLECTION_IDS,
        TEST_GRID_INFO_IDS,
    )


@pytest.fixture
def base_ispyb_conn():
    with patch("ispyb.open", mock_open()) as ispyb_connection:
        mock_mx_acquisition = MagicMock()
        mock_mx_acquisition.get_data_collection_group_params.side_effect = (
            lambda: deepcopy(MXAcquisition.get_data_collection_group_params())
        )

        mock_mx_acquisition.get_data_collection_params.side_effect = lambda: deepcopy(
            MXAcquisition.get_data_collection_params()
        )
        mock_mx_acquisition.get_dc_position_params.side_effect = lambda: deepcopy(
            MXAcquisition.get_dc_position_params()
        )
        mock_mx_acquisition.get_dc_grid_params.side_effect = lambda: deepcopy(
            MXAcquisition.get_dc_grid_params()
        )
        ispyb_connection.return_value.mx_acquisition = mock_mx_acquisition
        mock_core = MagicMock()

        def mock_retrieve_visit(visit_str):
            assert visit_str, "No visit id supplied"
            return TEST_SESSION_ID

        mock_core.retrieve_visit_id.side_effect = mock_retrieve_visit
        ispyb_connection.return_value.core = mock_core
        yield ispyb_connection


@pytest.fixture
def mock_ispyb_conn_multiscan(base_ispyb_conn):
    return _mock_ispyb_conn(
        base_ispyb_conn,
        TEST_POSITION_ID,
        TEST_DATA_COLLECTION_GROUP_ID,
        list(range(12, 24)),
        list(range(56, 68)),
    )


@pytest.fixture
def dummy_rotation_params():
    dummy_params = MultiRotationScan(
        **default_raw_params(
            "tests/test_data/parameter_json_files/good_test_one_multi_rotation_scan_parameters.json"
        )
    )
    dummy_params.sample_id = TEST_SAMPLE_ID
    return dummy_params


@pytest.fixture
def test_rotation_params():
    return MultiRotationScan(
        **raw_params_from_file(
            "tests/test_data/parameter_json_files/good_test_one_multi_rotation_scan_parameters.json"
        )
    )


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class XBPMAndTransmissionWrapperComposite:
    undulator: Undulator
    xbpm_feedback: XBPMFeedback
    attenuator: BinaryFilterAttenuator
    dcm: DCM


@pytest.fixture
def xbpm_and_transmission_wrapper_composite(
    undulator: Undulator,
    xbpm_feedback: XBPMFeedback,
    attenuator: BinaryFilterAttenuator,
    dcm: DCM,
) -> XBPMAndTransmissionWrapperComposite:
    return XBPMAndTransmissionWrapperComposite(
        undulator, xbpm_feedback, attenuator, dcm
    )


def assert_images_pixelwise_equal(actual, expected):
    with Image.open(expected) as expected_image:
        expected_bytes = expected_image.tobytes()
        with Image.open(actual) as actual_image:
            actual_bytes = actual_image.tobytes()
            # assert tries to be clever and takes forever if this is inlined and
            # the comparison fails
            bytes_expected_bytes = actual_bytes == expected_bytes
            assert bytes_expected_bytes, (
                f"Actual and expected images differ, {actual} != {expected}"
            )
