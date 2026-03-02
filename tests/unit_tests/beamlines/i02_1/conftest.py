import pytest

from mx_bluesky.beamlines.i02_1.composites import I02_1FgsParams
from mx_bluesky.common.parameters.components import get_param_version


@pytest.fixture
def fgs_params_two_d(tmp_path) -> I02_1FgsParams:
    return I02_1FgsParams(
        x_start_um=0,
        y_starts_um=[0],
        z_starts_um=[0],
        y_step_sizes_um=[10],
        omega_starts_deg=[0],
        parameter_model_version=get_param_version(),
        sample_id=0,
        visit="cm0000-0",
        file_name="test_file",
        storage_directory=str(tmp_path),
        x_steps=5,
        y_steps=[3],
        path_to_xtal_snapshot=tmp_path,
        beam_size_x=0,
        beam_size_y=0,
        microns_per_pixel_x=1,
        microns_per_pixel_y=1,
        upper_left_x=0,
        upper_left_y=0,
        detector_distance_mm=100,
    )
