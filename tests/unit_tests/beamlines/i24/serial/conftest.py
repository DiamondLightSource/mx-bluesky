from __future__ import annotations

from pathlib import Path

import bluesky.plan_stubs as bps
import pytest
from dodal.beamlines import i24
from dodal.devices.attenuator.attenuator import ReadOnlyAttenuator
from dodal.devices.i24.beam_center import DetectorBeamCenter
from dodal.devices.zebra.zebra import Zebra
from dodal.utils import AnyDeviceFactory
from ophyd_async.core import set_mock_value

from mx_bluesky.beamlines.i24.serial.fixed_target.ft_utils import ChipType
from mx_bluesky.beamlines.i24.serial.parameters import (
    ExtruderParameters,
    FixedTargetParameters,
    get_chip_format,
)
from mx_bluesky.beamlines.i24.serial.parameters.constants import DetectorName

from .....conftest import device_factories_for_beamline

TEST_PATH = Path("tests/test_data/test_daq_configuration")

TEST_LUT = {
    DetectorName.EIGER: TEST_PATH / "lookup/test_det_dist_converter.txt",
}


def fake_generator(value):
    yield from bps.null()
    return value


@pytest.fixture(scope="session")
def active_device_factories(active_device_factories) -> set[AnyDeviceFactory]:
    return active_device_factories | device_factories_for_beamline(i24)


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


@pytest.fixture
def zebra() -> Zebra:
    return i24.zebra.build(connect_immediately=True, mock=True)


@pytest.fixture
def eiger_beam_center() -> DetectorBeamCenter:
    bc: DetectorBeamCenter = i24.eiger_beam_center.build(
        connect_immediately=True, mock=True
    )
    set_mock_value(bc.beam_x, 1605)
    set_mock_value(bc.beam_y, 1702)
    return bc


@pytest.fixture
def attenuator() -> ReadOnlyAttenuator:
    attenuator: ReadOnlyAttenuator = i24.attenuator.build(
        connect_immediately=True, mock=True
    )
    set_mock_value(attenuator.actual_transmission, 1.0)
    return attenuator
