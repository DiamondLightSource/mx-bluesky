from pathlib import Path

import pytest

from mx_bluesky.beamlines.i24.serial.fixed_target.ft_utils import ChipType
from mx_bluesky.beamlines.i24.serial.parameters import (
    DetectorName,
    FixedTargetParameters,
    get_chip_format,
)

TEST_PATH = Path("tests/test_data/test_daq_configuration")

TEST_LUT = {
    DetectorName.EIGER: TEST_PATH / "lookup/test_det_dist_converter.txt",
}


@pytest.fixture
def dummy_params_with_pp():
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
        "pump_repeat": 3,
        "checker_pattern": False,
        "chip_map": [1],
        "laser_dwell_s": 0.02,
        "laser_delay_s": 0.05,
    }
    return FixedTargetParameters(**params)
