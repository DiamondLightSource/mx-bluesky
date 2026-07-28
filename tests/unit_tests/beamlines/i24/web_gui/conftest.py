import pytest
from dodal.beamlines import i24
from dodal.devices.attenuator.attenuator import EnumFilterAttenuator
from dodal.devices.beamlines.i24.beam_center import DetectorBeamCenter
from ophyd_async.core import set_mock_value

from mx_bluesky.beamlines.i24.serial.fixed_target.ft_utils import ChipType
from mx_bluesky.beamlines.i24.serial.parameters.experiment_parameters import (
    ExtruderParameters,
    FixedTargetParameters,
)
from mx_bluesky.beamlines.i24.serial.parameters.utils import get_chip_format


@pytest.fixture
def eiger_beam_center() -> DetectorBeamCenter:
    bc: DetectorBeamCenter = i24.eiger_beam_center.build(
        connect_immediately=True, mock=True
    )
    set_mock_value(bc.beam_x, 1605)
    set_mock_value(bc.beam_y, 1702)
    return bc


@pytest.fixture
def enum_attenuator() -> EnumFilterAttenuator:
    return i24.attenuator.build(connect_immediately=True, mock=True)


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
    return FixedTargetParameters(**params)  # type: ignore


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
    return ExtruderParameters(**params)  # type: ignore
