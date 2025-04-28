from __future__ import annotations

from pathlib import Path

import bluesky.plan_stubs as bps
import pytest
from dodal.beamlines import i24
from dodal.devices.hutch_shutter import (
    HUTCH_SAFE_FOR_OPERATIONS,
    HutchShutter,
    ShutterDemand,
    ShutterState,
)
from dodal.devices.i24.aperture import Aperture
from dodal.devices.i24.beam_center import DetectorBeamCenter
from dodal.devices.i24.beamstop import Beamstop
from dodal.devices.i24.dcm import DCM
from dodal.devices.i24.dual_backlight import DualBacklight
from dodal.devices.i24.focus_mirrors import FocusMirrorsMode, HFocusMode, VFocusMode
from dodal.devices.i24.pmac import PMAC
from dodal.devices.zebra.zebra import Zebra
from dodal.utils import AnyDeviceFactory
from ophyd_async.epics.motor import Motor
from ophyd_async.testing import callback_on_mock_put, get_mock_put, set_mock_value

from mx_bluesky.beamlines.i24.serial.fixed_target.ft_utils import ChipType
from mx_bluesky.beamlines.i24.serial.parameters import (
    DetectorName,
    ExtruderParameters,
    FixedTargetParameters,
    get_chip_format,
)

from .....conftest import device_factories_for_beamline


@pytest.fixture(scope="session")
def active_device_factories(active_device_factories) -> set[AnyDeviceFactory]:
    return active_device_factories | device_factories_for_beamline(i24)


TEST_PATH = Path("tests/test_data/test_daq_configuration")

TEST_LUT = {
    DetectorName.EIGER: TEST_PATH / "lookup/test_det_dist_converter.txt",
    DetectorName.PILATUS: TEST_PATH / "lookup/test_det_dist_converter.txt",
}


@pytest.fixture
def dummy_params_without_pp():
    oxford_defaults = get_chip_format(ChipType.Oxford)
    params = {
        "visit": "/tmp/dls/i24/fixed/foo",
        "directory": "bar",
        "filename": "chip",
        "exposure_time_s": 0.01,
        "detector_distance_mm": 100,
        "detector_name": "eiger",
        "transmission": 1.0,
        "num_exposures": 1,
        "chip": oxford_defaults.model_dump(),
        "map_type": 1,
        "pump_repeat": 0,
        "checker_pattern": False,
        "chip_map": [1],
    }
    return FixedTargetParameters(**params)


@pytest.fixture
def dummy_params_ex():
    params = {
        "visit": "/tmp/dls/i24/extruder/foo",
        "directory": "bar",
        "filename": "protein",
        "exposure_time_s": 0.1,
        "detector_distance_mm": 100,
        "detector_name": "eiger",
        "transmission": 1.0,
        "num_images": 10,
        "pump_status": False,
    }
    return ExtruderParameters(**params)


def fake_generator(value):
    yield from bps.null()
    return value


def patch_motor(motor: Motor, initial_position: float = 0):
    set_mock_value(motor.user_setpoint, initial_position)
    set_mock_value(motor.user_readback, initial_position)
    set_mock_value(motor.deadband, 0.001)
    set_mock_value(motor.motor_done_move, 1)
    set_mock_value(motor.velocity, 3)
    return callback_on_mock_put(
        motor.user_setpoint,
        lambda pos, *args, **kwargs: set_mock_value(motor.user_readback, pos),
    )


@pytest.fixture
def zebra(RE) -> Zebra:
    zebra = i24.zebra(connect_immediately=True, mock=True)

    def mock_disarm(_, wait):
        set_mock_value(zebra.pc.arm.armed, 0)

    def mock_arm(_, wait):
        set_mock_value(zebra.pc.arm.armed, 1)

    get_mock_put(zebra.pc.arm.arm_set).side_effect = mock_arm
    get_mock_put(zebra.pc.arm.disarm_set).side_effect = mock_disarm
    return zebra


@pytest.fixture
def shutter(RE) -> HutchShutter:
    shutter = i24.shutter(connect_immediately=True, mock=True)
    set_mock_value(shutter.interlock.status, HUTCH_SAFE_FOR_OPERATIONS)

    def set_status(value: ShutterDemand, *args, **kwargs):
        value_sta = ShutterState.OPEN if value == "Open" else ShutterState.CLOSED
        set_mock_value(shutter.status, value_sta)

    callback_on_mock_put(shutter.control, set_status)
    return shutter


@pytest.fixture
def detector_stage(RE):
    detector_motion = i24.detector_motion(connect_immediately=True, mock=True)

    with patch_motor(detector_motion.y), patch_motor(detector_motion.z):
        yield detector_motion


@pytest.fixture
def aperture(RE):
    aperture: Aperture = i24.aperture(connect_immediately=True, mock=True)
    with patch_motor(aperture.x), patch_motor(aperture.y):
        yield aperture


@pytest.fixture
def backlight(RE) -> DualBacklight:
    backlight = i24.backlight(connect_immediately=True, mock=True)
    return backlight


@pytest.fixture
def beamstop(RE):
    beamstop: Beamstop = i24.beamstop(connect_immediately=True, mock=True)

    with (
        patch_motor(beamstop.x),
        patch_motor(beamstop.y),
        patch_motor(beamstop.z),
        patch_motor(beamstop.y_rotation),
    ):
        yield beamstop


@pytest.fixture
def pmac(RE):
    pmac: PMAC = i24.pmac(connect_immediately=True, mock=True)
    with (
        patch_motor(pmac.x),
        patch_motor(pmac.y),
        patch_motor(pmac.z),
    ):
        yield pmac


@pytest.fixture
def dcm(RE) -> DCM:
    dcm = i24.dcm(connect_immediately=True, mock=True)
    return dcm


@pytest.fixture
def eiger_beam_center(RE) -> DetectorBeamCenter:
    bc: DetectorBeamCenter = i24.eiger_beam_center(connect_immediately=True, mock=True)
    set_mock_value(bc.beam_x, 1605)
    set_mock_value(bc.beam_y, 1702)
    return bc


@pytest.fixture
def pilatus_beam_center(RE) -> DetectorBeamCenter:
    bc: DetectorBeamCenter = i24.pilatus_beam_center(
        connect_immediately=True, mock=True
    )
    set_mock_value(bc.beam_x, 1298)
    set_mock_value(bc.beam_y, 1307)
    return bc


@pytest.fixture
def mirrors(RE) -> FocusMirrorsMode:
    mirrors: FocusMirrorsMode = i24.focus_mirrors(connect_immediately=True, mock=True)
    set_mock_value(mirrors.horizontal, HFocusMode.FOCUS_10)
    set_mock_value(mirrors.vertical, VFocusMode.FOCUS_10)
    return mirrors
