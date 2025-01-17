import os

import pytest

from mx_bluesky.common.utils.utils import convert_angstrom_to_eV
from mx_bluesky.hyperion.parameters.gridscan import HyperionSpecifiedThreeDGridScan
from mx_bluesky.hyperion.parameters.rotation import RotationScan

from ....conftest import (
    default_raw_gridscan_params,
    raw_params_from_file,
)


@pytest.fixture
def test_rotation_params():
    param_dict = raw_params_from_file(
        "tests/test_data/parameter_json_files/good_test_rotation_scan_parameters.json"
    )
    param_dict["storage_directory"] = "tests/test_data"
    param_dict["file_name"] = "TEST_FILENAME"
    param_dict["demand_energy_ev"] = 12700
    param_dict["scan_width_deg"] = 360.0
    params = RotationScan(**param_dict)
    params.x_start_um = 0
    params.y_start_um = 0
    params.z_start_um = 0
    params.exposure_time_s = 0.004
    return params


@pytest.fixture(params=[1050])
def test_fgs_params(request):
    assert request.param % 25 == 0, "Please use a multiple of 25 images"
    params = HyperionSpecifiedThreeDGridScan(**default_raw_gridscan_params())
    params.demand_energy_ev = convert_angstrom_to_eV(1.0)
    params.use_roi_mode = True
    first_scan_img = (request.param // 10) * 6
    second_scan_img = (request.param // 10) * 4
    params.x_steps = 5
    params.y_steps = first_scan_img // 5
    params.z_steps = second_scan_img // 5
    params.storage_directory = (
        os.path.dirname(os.path.realpath(__file__)) + "/test_data"
    )
    params.file_name = "dummy"
    yield params


def default_raw_params(
    json_file="tests/test_data/parameter_json_files/good_test_parameters.json",
):
    return raw_params_from_file(json_file)
