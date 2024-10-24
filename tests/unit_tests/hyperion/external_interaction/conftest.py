import os
from collections.abc import Callable, Sequence
from copy import deepcopy
from typing import Any
from unittest.mock import MagicMock, mock_open, patch

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
import pytest
from bluesky.run_engine import RunEngine
from ispyb.sp.mxacquisition import MXAcquisition
from ophyd.sim import SynAxis

from mx_bluesky.hyperion.external_interaction.callbacks.plan_reactive_callback import (
    PlanReactiveCallback,
)
from mx_bluesky.hyperion.parameters.gridscan import ThreeDGridScan
from mx_bluesky.hyperion.parameters.rotation import RotationScan
from mx_bluesky.hyperion.utils.utils import convert_angstrom_to_eV

from ....conftest import raw_params_from_file


class MockReactiveCallback(PlanReactiveCallback):
    activity_gated_start: MagicMock
    activity_gated_descriptor: MagicMock
    activity_gated_event: MagicMock
    activity_gated_stop: MagicMock

    def __init__(self, *, emit: Callable[..., Any] | None = None) -> None:
        super().__init__(MagicMock(), emit=emit)
        self.activity_gated_start = MagicMock(name="activity_gated_start")  # type: ignore
        self.activity_gated_descriptor = MagicMock(name="activity_gated_descriptor")  # type: ignore
        self.activity_gated_event = MagicMock(name="activity_gated_event")  # type: ignore
        self.activity_gated_stop = MagicMock(name="activity_gated_stop")  # type: ignore


@pytest.fixture
def mocked_test_callback():
    t = MockReactiveCallback()
    return t


@pytest.fixture
def RE_with_mock_callback(mocked_test_callback):
    RE = RunEngine()
    RE.subscribe(mocked_test_callback)
    yield RE, mocked_test_callback


def get_test_plan(callback_name):
    s = SynAxis(name="fake_signal")

    @bpp.run_decorator(md={"activate_callbacks": [callback_name]})
    def test_plan():
        yield from bps.create()
        yield from bps.read(s)  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
        yield from bps.save()

    return test_plan, s


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
    params = ThreeDGridScan(**default_raw_params())
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


def _mock_ispyb_conn(base_ispyb_conn, position_id, dcgid, dcids, giids):
    def upsert_data_collection(values):
        kvpairs = remap_upsert_columns(
            list(MXAcquisition.get_data_collection_params()), values
        )
        if kvpairs["id"]:
            return kvpairs["id"]
        else:
            return next(upsert_data_collection.i)  # pyright: ignore

    mx_acq = base_ispyb_conn.return_value.mx_acquisition
    mx_acq.upsert_data_collection.side_effect = upsert_data_collection
    mx_acq.update_dc_position.return_value = position_id
    mx_acq.upsert_data_collection_group.return_value = dcgid

    def upsert_dc_grid(values):
        kvpairs = remap_upsert_columns(list(MXAcquisition.get_dc_grid_params()), values)
        if kvpairs["id"]:
            return kvpairs["id"]
        else:
            return next(upsert_dc_grid.i)  # pyright: ignore

    upsert_data_collection.i = iter(dcids)  # pyright: ignore
    upsert_dc_grid.i = iter(giids)  # pyright: ignore

    mx_acq.upsert_dc_grid.side_effect = upsert_dc_grid
    return base_ispyb_conn


@pytest.fixture
def mock_ispyb_conn(base_ispyb_conn):
    return _mock_ispyb_conn(
        base_ispyb_conn,
        TEST_POSITION_ID,
        TEST_DATA_COLLECTION_GROUP_ID,
        TEST_DATA_COLLECTION_IDS,
        TEST_GRID_INFO_IDS,
    )


@pytest.fixture
def mock_ispyb_conn_multiscan(base_ispyb_conn):
    return _mock_ispyb_conn(
        base_ispyb_conn,
        TEST_POSITION_ID,
        TEST_DATA_COLLECTION_GROUP_ID,
        list(range(12, 24)),
        list(range(56, 68)),
    )


def mx_acquisition_from_conn(mock_ispyb_conn) -> MagicMock:
    return mock_ispyb_conn.return_value.__enter__.return_value.mx_acquisition


def assert_upsert_call_with(call, param_template, expected: dict):
    actual = remap_upsert_columns(list(param_template), call.args[0])
    assert actual == dict(param_template | expected)


TEST_DATA_COLLECTION_IDS = (12, 13)
TEST_DATA_COLLECTION_GROUP_ID = 34
TEST_GRID_INFO_IDS = (56, 57)
TEST_POSITION_ID = 78
TEST_SESSION_ID = 90
EXPECTED_START_TIME = "2024-02-08 14:03:59"
EXPECTED_END_TIME = "2024-02-08 14:04:01"


def remap_upsert_columns(keys: Sequence[str], values: list):
    return dict(zip(keys, values, strict=False))


@pytest.fixture
def base_ispyb_conn():
    with patch("ispyb.open", mock_open()) as ispyb_connection:
        mock_mx_acquisition = MagicMock()
        mock_mx_acquisition.get_data_collection_group_params.side_effect = (
            lambda: deepcopy(MXAcquisition.get_data_collection_group_params())
        )

        mock_mx_acquisition.get_data_collection_params.side_effect = lambda: deepcopy(
            MXAcquisition.get_data_collection_params()
        )
        mock_mx_acquisition.get_dc_position_params.side_effect = lambda: deepcopy(
            MXAcquisition.get_dc_position_params()
        )
        mock_mx_acquisition.get_dc_grid_params.side_effect = lambda: deepcopy(
            MXAcquisition.get_dc_grid_params()
        )
        ispyb_connection.return_value.mx_acquisition = mock_mx_acquisition
        mock_core = MagicMock()

        def mock_retrieve_visit(visit_str):
            assert visit_str, "No visit id supplied"
            return TEST_SESSION_ID

        mock_core.retrieve_visit_id.side_effect = mock_retrieve_visit
        ispyb_connection.return_value.core = mock_core
        yield ispyb_connection


@pytest.fixture
def dummy_rotation_params():
    dummy_params = RotationScan(
        **default_raw_params(
            "tests/test_data/parameter_json_files/good_test_rotation_scan_parameters.json"
        )
    )
    dummy_params.sample_id = TEST_SAMPLE_ID
    return dummy_params


TEST_SAMPLE_ID = 364758
TEST_BARCODE = "12345A"


def default_raw_params(
    json_file="tests/test_data/parameter_json_files/good_test_parameters.json",
):
    return raw_params_from_file(json_file)
