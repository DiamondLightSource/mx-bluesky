import pytest
from dodal.beamlines import i02_1

from mx_bluesky.beamlines.i02_1.parameters import I02_1FgsParams
from mx_bluesky.common.parameters.components import (
    IspybExperimentType,
    get_param_version,
)
from mx_bluesky.common.parameters.gridscan import GridScanParams


@pytest.fixture
def fgs_params_two_d(tmp_path) -> I02_1FgsParams:
    return I02_1FgsParams(
        parameter_model_version=get_param_version(),
        sample_id=0,
        visit="cm0000-0",
        file_name="test_file",
        storage_directory=str(tmp_path),
        path_to_xtal_snapshot=tmp_path,
        beam_size_x=0,
        beam_size_y=0,
        microns_per_pixel_x=1,
        microns_per_pixel_y=1,
        upper_left_x=0,
        upper_left_y=0,
        detector_distance_mm=100,
        ispyb_experiment_type=IspybExperimentType.SAD,
    )


@pytest.fixture
def grid_scan_params():
    return GridScanParams(
        x_start_um=0,
        y_starts_um=[0],
        z_starts_um=[0],
        x_step_size_um=20,
        y_step_sizes_um=[20],
        omega_starts_deg=[0],
        x_steps=5,
        y_steps=[3],
    )


@pytest.fixture(autouse=True)
def always_use_i02_1_beamline(monkeypatch, patch_beamline_env_variable):
    monkeypatch.setenv("BEAMLINE", "i02-1")


@pytest.fixture()
def goniometer():
    return i02_1.goniometer.build(connect_immediately=True, mock=True)
