import json
from pathlib import Path
from unittest.mock import patch

import pytest
from dodal.devices.aperturescatterguard import ApertureValue
from pydantic import ValidationError

from mx_bluesky.common.external_interaction.callbacks.common.grid_detection_callback import (
    GridParamUpdate,
)
from mx_bluesky.common.parameters.components import DiffractionExperimentWithSample
from mx_bluesky.common.parameters.constants import GridscanParamConstants
from mx_bluesky.common.parameters.gridscan import GridScanParams
from mx_bluesky.common.parameters.rotation import (
    SingleRotationScan,
)
from mx_bluesky.hyperion.parameters.gridscan import (
    OddYStepsError,
    create_detector_params_with_hyperion_feature_settings,
    panda_fast_gridscan_params,
)
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect

from ....conftest import raw_params_from_file


@pytest.fixture(autouse=True)
def always_use_beamline_i03(use_beamline_i03): ...


@pytest.fixture
def load_centre_collect_params_with_panda(tmp_path, request):
    params = raw_params_from_file(
        "tests/test_data/parameter_json_files/good_test_load_centre_collect_params.json",
        tmp_path,
    )
    params["features"]["use_panda_for_gridscan"] = True
    if params_dict := getattr(request, "param", {}):
        for k, v in params_dict.items():
            params.setdefault("features", {})[k] = v
    return LoadCentreCollect(**params)


@pytest.fixture()
def minimal_3d_gridscan_params():
    return {
        "sample_id": 123,
        "x_start_um": 0.123,
        "y_starts_um": [0.777, 2],
        "z_starts_um": [0.05, 2],
        "parameter_model_version": "6.0.0",
        "visit": "cm12345",
        "file_name": "test_file_name",
        "x_steps": 5,
        "y_steps": [7, 9],
        "storage_directory": "/tmp/dls/i03/data/2024/cm31105-4/xraycentring/123456/",
    }


@pytest.fixture()
def minimal_gridscan_params() -> GridScanParams:
    return GridScanParams(
        omega_starts_deg=[0, 90],
        x_start_um=0.123,
        y_starts_um=[0.777, 2],
        z_starts_um=[0.05, 2],
        x_steps=5,
        y_steps=[7, 9],
    )


def get_empty_grid_parameters() -> GridParamUpdate:
    return {
        "x_start_um": 1,
        "y_starts_um": [1, 1],
        "z_starts_um": [1, 1],
        "x_steps": 1,
        "y_steps": [1, 1],
        "x_step_size_um": 1,
        "y_step_sizes_um": [1, 1],
    }


def test_minimal_3d_gridscan_params(minimal_gridscan_params: GridScanParams):
    assert all(
        {"sam_x", "sam_y", "sam_z"} == set(scan_point.keys())
        for scan_point in minimal_gridscan_params.scan_points
    )

    assert minimal_gridscan_params.scan_indices == [0, 35]


def test_minimal_expt_params(
    minimal_diffraction_expt_with_sample: DiffractionExperimentWithSample,
):
    assert minimal_diffraction_expt_with_sample.num_images == (5 * 7 + 5 * 9)
    assert (
        minimal_diffraction_expt_with_sample.exposure_time_s
        == GridscanParamConstants.EXPOSURE_TIME_S
    )


def test_cant_do_panda_fgs_with_odd_y_steps(
    minimal_diffraction_expt_with_sample: DiffractionExperimentWithSample,
    minimal_gridscan_params: GridScanParams,
):
    with pytest.raises(OddYStepsError):
        _ = panda_fast_gridscan_params(
            minimal_diffraction_expt_with_sample, minimal_gridscan_params
        )


def test_serialise_deserialise(minimal_gridscan_params: GridScanParams):
    serialised = json.loads(minimal_gridscan_params.model_dump_json())
    deserialised = GridScanParams(**serialised)
    assert deserialised == minimal_gridscan_params


def test_serialize_deserialize_diff_expt_with_sample(
    minimal_diffraction_expt_with_sample: DiffractionExperimentWithSample,
):
    serialised = json.loads(minimal_diffraction_expt_with_sample.model_dump_json())
    deserialised = DiffractionExperimentWithSample(**serialised)
    assert deserialised == minimal_diffraction_expt_with_sample


@pytest.mark.parametrize(
    "version, valid",
    [
        ("4.3.0", False),
        ("7.3.7", False),
        ("5.0.0", False),
        ("5.3.0", False),
        ("5.3.7", False),
        ("6.0.0", True),
    ],
)
def test_param_version(minimal_diffraction_expt_with_sample, version: str, valid: bool):
    values = minimal_diffraction_expt_with_sample.model_dump()
    values["parameter_model_version"] = version
    if valid:
        _ = DiffractionExperimentWithSample(**values)
    else:
        with pytest.raises(ValidationError):
            _ = DiffractionExperimentWithSample(**values)


def test_default_snapshot_path(
    minimal_diffraction_expt_with_sample: DiffractionExperimentWithSample,
):
    assert minimal_diffraction_expt_with_sample.snapshot_directory == Path(
        "/tmp/dls/i03/data/2024/cm31105-4/xraycentring/123456/snapshots"
    )

    params_with_snapshot_path = minimal_diffraction_expt_with_sample.model_dump()
    params_with_snapshot_path["snapshot_directory"] = "/tmp/my_snapshots"

    gridscan_params_with_snapshot_path = DiffractionExperimentWithSample(
        **params_with_snapshot_path
    )
    assert gridscan_params_with_snapshot_path.snapshot_directory == Path(
        "/tmp/my_snapshots"
    )


def test_osc_is_used(tmp_path):
    raw_params = raw_params_from_file(
        "tests/test_data/parameter_json_files/good_test_rotation_scan_parameters.json",
        tmp_path,
    )
    for osc in [0.001, 0.05, 0.1, 0.2, 0.75, 1, 1.43]:
        raw_params["rotation_increment_deg"] = osc
        params = SingleRotationScan(**raw_params)
        assert params.rotation_increment_deg == osc
        assert params.num_images == int(params.scan_width_deg / osc)


def test_selected_aperture_uses_default(tmp_path):
    raw_params = raw_params_from_file(
        "tests/test_data/parameter_json_files/good_test_rotation_scan_parameters.json",
        tmp_path,
    )
    raw_params["selected_aperture"] = None
    params = SingleRotationScan(**raw_params)
    assert params.selected_aperture == ApertureValue.LARGE


@pytest.mark.parametrize(
    "enable_gpu",
    [
        True,
        False,
    ],
)
@patch("mx_bluesky.common.parameters.components.os")
def test_create_detector_params_with_hyperion_feature_settings_sets_dev_shm_enabled_if_use_gpu_results_enabled(
    _, enable_gpu, minimal_diffraction_expt_with_sample: DiffractionExperimentWithSample
):
    properties_path = (
        "tests/test_data/test_domain_properties_with_no_gpu"
        if not enable_gpu
        else "tests/test_data/test_domain_properties"
    )
    with patch(
        "mx_bluesky.hyperion.external_interaction.config_server.GDA_DOMAIN_PROPERTIES_PATH",
        new=properties_path,
    ):
        detector_params = create_detector_params_with_hyperion_feature_settings(
            minimal_diffraction_expt_with_sample
        )
        assert detector_params.enable_dev_shm == enable_gpu
