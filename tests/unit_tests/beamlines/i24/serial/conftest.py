from __future__ import annotations

from pathlib import Path

import bluesky.plan_stubs as bps
import pytest
from dodal.beamlines import i24
from dodal.devices.attenuator.attenuator import ReadOnlyAttenuator
from dodal.devices.hutch_shutter import (
    HUTCH_SAFE_FOR_OPERATIONS,
    HutchShutter,
    ShutterDemand,
    ShutterState,
)
from dodal.devices.i24.beam_center import DetectorBeamCenter
from dodal.devices.i24.dcm import DCM
from dodal.devices.i24.dual_backlight import DualBacklight
from dodal.devices.i24.focus_mirrors import FocusMirrorsMode, HFocusMode, VFocusMode
from dodal.devices.zebra.zebra import Zebra
from dodal.utils import AnyDeviceFactory
from ophyd_async.core import callback_on_mock_put, set_mock_value

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


@pytest.fixture
def zebra() -> Zebra:
    return i24.zebra.build(connect_immediately=True, mock=True)


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
def detector_stage():
    return i24.detector_motion.build(connect_immediately=True, mock=True)


@pytest.fixture
def aperture():
    return i24.aperture.build(connect_immediately=True, mock=True)


@pytest.fixture
def backlight() -> DualBacklight:
    return i24.backlight.build(connect_immediately=True, mock=True)


@pytest.fixture
def beamstop():
    return i24.beamstop.build(connect_immediately=True, mock=True)


@pytest.fixture
def pmac():
    return i24.pmac.build(connect_immediately=True, mock=True)


@pytest.fixture
def dcm() -> DCM:
    return i24.dcm.build(connect_immediately=True, mock=True)


@pytest.fixture
def eiger_beam_center() -> DetectorBeamCenter:
    bc: DetectorBeamCenter = i24.eiger_beam_center.build(
        connect_immediately=True, mock=True
    )
    set_mock_value(bc.beam_x, 1605)
    set_mock_value(bc.beam_y, 1702)
    return bc


@pytest.fixture
def mirrors() -> FocusMirrorsMode:
    mirrors: FocusMirrorsMode = i24.focus_mirrors.build(
        connect_immediately=True, mock=True
    )
    set_mock_value(mirrors.horizontal, HFocusMode.FOCUS_10)
    set_mock_value(mirrors.vertical, VFocusMode.FOCUS_10)
    return mirrors


@pytest.fixture
def attenuator() -> ReadOnlyAttenuator:
    attenuator: ReadOnlyAttenuator = i24.attenuator.build(
        connect_immediately=True, mock=True
    )
    set_mock_value(attenuator.actual_transmission, 1.0)
    return attenuator
