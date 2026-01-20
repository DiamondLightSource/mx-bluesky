import pytest
from dodal.beamlines import i24
from dodal.devices.hutch_shutter import (
    HUTCH_SAFE_FOR_OPERATIONS,
    HutchShutter,
    ShutterDemand,
    ShutterState,
)
from dodal.devices.i24.aperture import Aperture
from dodal.devices.i24.beamstop import Beamstop
from dodal.devices.i24.dcm import DCM
from dodal.devices.i24.dual_backlight import DualBacklight
from dodal.devices.i24.focus_mirrors import FocusMirrorsMode, HFocusMode, VFocusMode
from dodal.devices.i24.pmac import PMAC
from dodal.devices.motors import YZStage
from ophyd_async.core import callback_on_mock_put, set_mock_value


@pytest.fixture
def shutter() -> HutchShutter:
    shutter = i24.shutter.build(connect_immediately=True, mock=True)
    set_mock_value(shutter.interlock.status, HUTCH_SAFE_FOR_OPERATIONS)

    def set_status(value: ShutterDemand, *args, **kwargs):
        value_sta = ShutterState.OPEN if value == "Open" else ShutterState.CLOSED
        set_mock_value(shutter.status, value_sta)

    callback_on_mock_put(shutter.control, set_status)
    return shutter


@pytest.fixture
def backlight() -> DualBacklight:
    return i24.backlight.build(connect_immediately=True, mock=True)


@pytest.fixture
def pmac() -> PMAC:
    return i24.pmac.build(connect_immediately=True, mock=True)


@pytest.fixture
def detector_stage() -> YZStage:
    return i24.detector_motion.build(connect_immediately=True, mock=True)


@pytest.fixture
def aperture() -> Aperture:
    return i24.aperture.build(connect_immediately=True, mock=True)


@pytest.fixture
def beamstop() -> Beamstop:
    return i24.beamstop.build(connect_immediately=True, mock=True)


@pytest.fixture
def dcm() -> DCM:
    return i24.dcm.build(connect_immediately=True, mock=True)


@pytest.fixture
def mirrors() -> FocusMirrorsMode:
    mirrors: FocusMirrorsMode = i24.focus_mirrors.build(
        connect_immediately=True, mock=True
    )
    set_mock_value(mirrors.horizontal, HFocusMode.FOCUS_10)
    set_mock_value(mirrors.vertical, VFocusMode.FOCUS_10)
    return mirrors
