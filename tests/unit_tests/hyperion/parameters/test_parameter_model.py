import json
from pathlib import Path
from unittest.mock import patch

import pytest
from dodal.devices.aperturescatterguard import ApertureValue
from pydantic import ValidationError

from mx_bluesky.common.parameters.constants import GridscanParamConstants
from mx_bluesky.common.parameters.gridscan import RobotLoadThenCentre
from mx_bluesky.hyperion.parameters.gridscan import (
    HyperionThreeDGridScan,
    OddYStepsException,
)
from mx_bluesky.hyperion.parameters.rotation import RotationScan

from ....conftest import raw_params_from_file


@pytest.fixture
def minimal_3d_gridscan_params():
    return {
        "sample_id": 123,
        "x_start_um": 0.123,
        "y_start_um": 0.777,
        "z_start_um": 0.05,
        "parameter_model_version": "5.0.0",
        "visit": "cm12345",
        "file_name": "test_file_name",
        "y2_start_um": 2,
        "z2_start_um": 2,
        "x_steps": 5,
        "y_steps": 7,
        "z_steps": 9,
        "storage_directory": "/tmp/dls/i03/data/2024/cm31105-4/xraycentring/123456/",
    }


def test_minimal_3d_gridscan_params(minimal_3d_gridscan_params):
    test_params = HyperionThreeDGridScan(**minimal_3d_gridscan_params)
    assert {"sam_x", "sam_y", "sam_z"} == set(test_params.scan_points.keys())
    assert test_params.scan_indices == [0, 35]
    assert test_params.num_images == (5 * 7 + 5 * 9)
    assert test_params.exposure_time_s == GridscanParamConstants.EXPOSURE_TIME_S


def test_cant_do_panda_fgs_with_odd_y_steps(minimal_3d_gridscan_params):
    test_params = HyperionThreeDGridScan(**minimal_3d_gridscan_params)
    with pytest.raises(OddYStepsException):
        _ = test_params.panda_FGS_params
    assert test_params.FGS_params


def test_serialise_deserialise(minimal_3d_gridscan_params):
    test_params = HyperionThreeDGridScan(**minimal_3d_gridscan_params)
    serialised = json.loads(test_params.model_dump_json())
    deserialised = HyperionThreeDGridScan(**serialised)
    assert deserialised.demand_energy_ev is None
    assert deserialised.visit == "cm12345"
    assert deserialised.x_start_um == 0.123


def test_param_version(minimal_3d_gridscan_params):
    with pytest.raises(ValidationError):
        minimal_3d_gridscan_params["parameter_model_version"] = "4.3.0"
        _ = HyperionThreeDGridScan(**minimal_3d_gridscan_params)
    minimal_3d_gridscan_params["parameter_model_version"] = "5.0.0"
    _ = HyperionThreeDGridScan(**minimal_3d_gridscan_params)
    minimal_3d_gridscan_params["parameter_model_version"] = "5.3.0"
    _ = HyperionThreeDGridScan(**minimal_3d_gridscan_params)
    minimal_3d_gridscan_params["parameter_model_version"] = "5.3.7"
    _ = HyperionThreeDGridScan(**minimal_3d_gridscan_params)
    with pytest.raises(ValidationError):
        minimal_3d_gridscan_params["parameter_model_version"] = "6.3.7"
        _ = HyperionThreeDGridScan(**minimal_3d_gridscan_params)


def test_robot_load_then_centre_params():
    params = {
        "parameter_model_version": "5.0.0",
        "sample_id": 123456,
        "visit": "cm12345",
        "file_name": "file_name",
        "storage_directory": "/tmp/dls/i03/data/2024/cm31105-4/xraycentring/123456/",
    }
    params["detector_distance_mm"] = 200
    test_params = RobotLoadThenCentre(**params)
    assert test_params.detector_params


def test_default_snapshot_path(minimal_3d_gridscan_params):
    gridscan_params = HyperionThreeDGridScan(**minimal_3d_gridscan_params)
    assert gridscan_params.snapshot_directory == Path(
        "/tmp/dls/i03/data/2024/cm31105-4/xraycentring/123456/snapshots"
    )

    params_with_snapshot_path = dict(minimal_3d_gridscan_params)
    params_with_snapshot_path["snapshot_directory"] = "/tmp/my_snapshots"

    gridscan_params_with_snapshot_path = HyperionThreeDGridScan(
        **params_with_snapshot_path
    )
    assert gridscan_params_with_snapshot_path.snapshot_directory == Path(
        "/tmp/my_snapshots"
    )


def test_osc_is_used():
    raw_params = raw_params_from_file(
        "tests/test_data/parameter_json_files/good_test_rotation_scan_parameters.json"
    )
    for osc in [0.001, 0.05, 0.1, 0.2, 0.75, 1, 1.43]:
        raw_params["rotation_increment_deg"] = osc
        params = RotationScan(**raw_params)
        assert params.rotation_increment_deg == osc
        assert params.num_images == int(params.scan_width_deg / osc)


def test_selected_aperture_uses_default():
    raw_params = raw_params_from_file(
        "tests/test_data/parameter_json_files/good_test_rotation_scan_parameters.json"
    )
    raw_params["selected_aperture"] = None
    params = RotationScan(**raw_params)
    assert params.selected_aperture == ApertureValue.LARGE


def test_feature_flags_overriden_if_supplied(minimal_3d_gridscan_params):
    test_params = HyperionThreeDGridScan(**minimal_3d_gridscan_params)
    assert test_params.features.use_panda_for_gridscan is False
    assert test_params.features.compare_cpu_and_gpu_zocalo is False
    minimal_3d_gridscan_params["features"] = {
        "use_panda_for_gridscan": True,
        "compare_cpu_and_gpu_zocalo": True,
    }
    test_params = HyperionThreeDGridScan(**minimal_3d_gridscan_params)
    assert test_params.features.compare_cpu_and_gpu_zocalo
    assert test_params.features.use_panda_for_gridscan
    # Config server shouldn't update values which were explicitly provided
    test_params.features.update_self_from_server()
    assert test_params.features.compare_cpu_and_gpu_zocalo
    assert test_params.features.use_panda_for_gridscan


@patch("mx_bluesky.common.parameters.components.os")
def test_gpu_enabled_if_use_gpu_or_compare_gpu_enabled(_, minimal_3d_gridscan_params):
    minimal_3d_gridscan_params["detector_distance_mm"] = 100

    grid_scan = HyperionThreeDGridScan(**minimal_3d_gridscan_params)
    assert not grid_scan.detector_params.enable_dev_shm

    minimal_3d_gridscan_params["features"] = {
        "compare_cpu_and_gpu_zocalo": True,
    }
    grid_scan = HyperionThreeDGridScan(**minimal_3d_gridscan_params)
    assert grid_scan.detector_params.enable_dev_shm
