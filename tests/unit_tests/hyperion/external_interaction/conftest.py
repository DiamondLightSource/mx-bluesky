import os
from pathlib import Path

import pytest

from mx_bluesky.common.parameters.components import DiffractionExperimentWithSample
from mx_bluesky.common.parameters.gridscan import GridScanParams
from mx_bluesky.common.parameters.rotation import (
    SingleRotationScan,
)
from mx_bluesky.common.utils.utils import convert_angstrom_to_ev

from ....conftest import (
    nexus_test_diffraction_expt_with_sample,
    raw_params_from_file,
)


@pytest.fixture(autouse=True)
def always_use_i03_beamline(use_beamline_i03): ...


@pytest.fixture
def test_rotation_params(tmp_path):
    param_dict = raw_params_from_file(
        "tests/test_data/parameter_json_files/good_test_rotation_scan_parameters.json",
        tmp_path,
    )
    param_dict["storage_directory"] = "tests/test_data"
    param_dict["file_name"] = "TEST_FILENAME"
    param_dict["demand_energy_ev"] = 12700
    param_dict["scan_width_deg"] = 360.0
    params = SingleRotationScan(**param_dict)
    params.x_start_um = 0
    params.y_start_um = 0
    params.exposure_time_s = 0.004
    return params


@pytest.fixture(params=[1050])
def test_three_d_grid_params(
    request, grid_scan_params_3d: GridScanParams
) -> GridScanParams:
    assert request.param % 25 == 0, "Please use a multiple of 25 images"
    params = grid_scan_params_3d
    first_scan_img = (request.param // 10) * 6
    second_scan_img = (request.param // 10) * 4
    params.x_steps = 5
    params.y_steps[0] = first_scan_img // 5
    params.y_steps[1] = second_scan_img // 5
    return params


@pytest.fixture()
def expt_params_for_nexus_tests(tmp_path: Path) -> DiffractionExperimentWithSample:
    params: DiffractionExperimentWithSample = nexus_test_diffraction_expt_with_sample(
        tmp_path
    )
    params.demand_energy_ev = convert_angstrom_to_ev(1.0)
    params.use_roi_mode = True
    params.storage_directory = (
        os.path.dirname(os.path.realpath(__file__)) + "/test_data"
    )
    params.file_name = "dummy"

    return params
