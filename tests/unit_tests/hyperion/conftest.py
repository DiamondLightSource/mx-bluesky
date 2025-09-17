import asyncio
from collections.abc import Generator
from concurrent.futures import Executor, Future, ThreadPoolExecutor
from importlib import resources
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from dodal.beamlines import i03

from mx_bluesky.common.external_interaction.ispyb.data_model import (
    DataCollectionGroupInfo,
)
from mx_bluesky.common.parameters.components import PARAMETER_VERSION
from mx_bluesky.hyperion.parameters.components import Wait
from mx_bluesky.hyperion.parameters.gridscan import (
    GridScanWithEdgeDetect,
    HyperionSpecifiedThreeDGridScan,
)
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect
from mx_bluesky.hyperion.parameters.rotation import RotationScan
from mx_bluesky.hyperion.runner import BaseRunner
from tests.conftest import (
    raw_params_from_file,
)

i03.DAQ_CONFIGURATION_PATH = "tests/test_data/test_daq_configuration"
BANNED_PATHS = [Path("/dls"), Path("/dls_sw")]

# Time to wait for the whole test script thread to complete
TEST_SCRIPT_TIMEOUT_S = 2

# Time to wait for the test to progress to the next step
AGAMEMNON_WAIT_FOR_TEST_STEP_S = 0.2

AGAMEMNON_WAIT_INSTRUCTION = Wait.model_validate(
    {
        "duration_s": AGAMEMNON_WAIT_FOR_TEST_STEP_S,
        "parameter_model_version": PARAMETER_VERSION,
    }
)


@pytest.fixture(scope="session")
def executor() -> Generator[Executor, Any, Any]:
    ex = ThreadPoolExecutor(max_workers=1, thread_name_prefix="test thread")
    yield ex
    ex.shutdown(wait=True)


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


@pytest.fixture
def test_fgs_params(tmp_path):
    return HyperionSpecifiedThreeDGridScan(
        **raw_params_from_file(
            "tests/test_data/parameter_json_files/good_test_parameters.json", tmp_path
        )
    )


@pytest.fixture(params=[False, True])
def test_omega_flip(request):
    with patch(
        "mx_bluesky.hyperion.parameters.constants.I03Constants.OMEGA_FLIP",
        new=request.param,
    ):
        yield request.param


@pytest.fixture
def fgs_params_use_panda(tmp_path):
    with patch(
        "mx_bluesky.common.external_interaction.config_server.GDA_DOMAIN_PROPERTIES_PATH",
        new="tests/test_data/test_domain_properties_with_panda",
    ):
        params = raw_params_from_file(
            "tests/test_data/parameter_json_files/good_test_parameters.json",
            tmp_path,
        )
        yield HyperionSpecifiedThreeDGridScan(**params)


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


def launch_test_in_runner_event_loop(
    async_func, udc_runner: BaseRunner, executor
) -> Future:
    """Launch the async func in a separate thread because the RunEngine under
    test must run in the main thread and block our test code, and return
    result and any exception to the caller."""

    def _launch_in_new_thread():
        future = asyncio.run_coroutine_threadsafe(async_func(), udc_runner.RE.loop)
        return future.result(TEST_SCRIPT_TIMEOUT_S)

    return executor.submit(_launch_in_new_thread)
