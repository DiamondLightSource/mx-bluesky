from unittest.mock import MagicMock

import pytest
import responses
from dodal.beamlines import i24
from dodal.devices.beamlines.i24.aperture import Aperture
from dodal.devices.beamlines.i24.beamstop import Beamstop
from dodal.devices.beamlines.i24.dcm import DCM
from dodal.devices.beamlines.i24.dual_backlight import DualBacklight
from dodal.devices.beamlines.i24.focus_mirrors import (
    FocusMirrorsMode,
    HFocusMode,
    VFocusMode,
)
from dodal.devices.beamlines.i24.pmac import PMAC
from dodal.devices.hutch_shutter import (
    InterlockedHutchShutter,
    ShutterDemand,
    ShutterState,
)
from dodal.devices.motors import YZStage
from ophyd_async.core import callback_on_mock_put, set_mock_value

from mx_bluesky.beamlines.i24.dcserver import SERVER_ENV_VAR, TOKEN_ENV_VAR

TEST_DCSERVER_URL = "https://dcserver.test"


@pytest.fixture(autouse=True)
def mock_requests(monkeypatch: pytest.MonkeyPatch):
    """Every request an i24 test makes, answered here or refused.

    The rotation plan posts to ssx-dcserver as an ordinary call rather than through a
    device, so without this a test that forgot to say otherwise would write to the real
    ISPyB. Anything not registered raises ConnectionError, which is what makes that
    impossible rather than merely unlikely - register what your test expects.

    The server and token are overridden too, so no test can read the beamline's
    credentials or so much as name the production server.
    """
    monkeypatch.setenv(TOKEN_ENV_VAR, "a-test-token")
    monkeypatch.setenv(SERVER_ENV_VAR, TEST_DCSERVER_URL)
    with responses.RequestsMock(assert_all_requests_are_fired=False) as mock:
        yield mock


@pytest.fixture
def shutter() -> InterlockedHutchShutter:
    shutter = i24.shutter.build(connect_immediately=True, mock=True)
    shutter.interlock._safe_to_operate = MagicMock(return_value=True)

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


@pytest.fixture()
def use_i24_beamline(monkeypatch, patch_beamline_env_variable):
    monkeypatch.setenv("BEAMLINE", "i24")
