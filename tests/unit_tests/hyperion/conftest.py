from importlib import resources
from pathlib import Path
from unittest.mock import patch

import pytest
from dodal.beamlines import i03
from dodal.devices.oav.oav_parameters import OAVParameters

from mx_bluesky.common.external_interaction.ispyb.data_model import (
    DataCollectionGroupInfo,
)
from mx_bluesky.hyperion.external_interaction.config_server import HyperionFeatureFlags
from mx_bluesky.hyperion.parameters.gridscan import (
    GridScanWithEdgeDetect,
    HyperionSpecifiedThreeDGridScan,
)
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect
from mx_bluesky.hyperion.parameters.rotation import RotationScan
from tests.conftest import (
    raw_params_from_file,
)

i03.DAQ_CONFIGURATION_PATH = "tests/test_data/test_daq_configuration"
BANNED_PATHS = [Path("/dls"), Path("/dls_sw")]


@pytest.fixture
def load_centre_collect_params(tmp_path):
    json_dict = raw_params_from_file(
        "tests/test_data/parameter_json_files/good_test_load_centre_collect_params.json",
        tmp_path,
    )
    return LoadCentreCollect(**json_dict)


@pytest.fixture(autouse=True)
def patch_open_to_prevent_dls_reads_in_tests():
    unpatched_open = open
    assert __package__
    project_folder = resources.files(__package__)
    assert isinstance(project_folder, Path)
    project_folder = project_folder.parent.parent.parent

    def patched_open(*args, **kwargs):
        requested_path = Path(args[0])
        if requested_path.is_absolute():
            for p in BANNED_PATHS:
                assert not requested_path.is_relative_to(p), (
                    f"Attempt to open {requested_path} from inside a unit test"
                )
        return unpatched_open(*args, **kwargs)

    with patch("builtins.open", side_effect=patched_open):
        yield []


@pytest.fixture
def test_rotation_params_nomove(tmp_path):
    return RotationScan(
        **raw_params_from_file(
            "tests/test_data/parameter_json_files/good_test_one_multi_rotation_scan_parameters_nomove.json",
            tmp_path,
        )
    )


@pytest.fixture
def test_multi_rotation_params(tmp_path):
    return RotationScan(
        **raw_params_from_file(
            "tests/test_data/parameter_json_files/good_test_multi_rotation_scan_parameters.json",
            tmp_path,
        )
    )


def oav_parameters_for_rotation(test_config_files) -> OAVParameters:
    return OAVParameters(oav_config_json=test_config_files["oav_config_json"])


@pytest.fixture
def test_fgs_params(tmp_path):
    return HyperionSpecifiedThreeDGridScan(
        **raw_params_from_file(
            "tests/test_data/parameter_json_files/good_test_parameters.json", tmp_path
        )
    )


@pytest.fixture
def test_panda_fgs_params(test_fgs_params: HyperionSpecifiedThreeDGridScan):
    test_fgs_params.features.use_panda_for_gridscan = True
    return test_fgs_params


@pytest.fixture
def feature_flags():
    return HyperionFeatureFlags()


@pytest.fixture
def test_full_grid_scan_params(tmp_path):
    params = raw_params_from_file(
        "tests/test_data/parameter_json_files/good_test_grid_with_edge_detect_parameters.json",
        tmp_path,
    )
    return GridScanWithEdgeDetect(**params)


def dummy_rotation_data_collection_group_info():
    return DataCollectionGroupInfo(
        visit_string="cm31105-4",
        experiment_type="SAD",
        sample_id=364758,
    )
