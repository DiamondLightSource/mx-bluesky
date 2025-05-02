import asyncio
import time
from collections.abc import Callable
from functools import partial
from unittest.mock import MagicMock, patch

import pytest
from bluesky.run_engine import RunEngine
from dodal.beamlines import i03
from dodal.common.beamlines import beamline_parameters
from dodal.devices.aperturescatterguard import ApertureValue
from dodal.devices.smargon import Smargon
from dodal.devices.synchrotron import SynchrotronMode
from dodal.devices.zocalo import ZocaloResults, ZocaloTrigger
from event_model.documents import Event
from ophyd_async.core import AsyncStatus
from ophyd_async.testing import set_mock_value

from mx_bluesky.common.external_interaction.callbacks.common.zocalo_callback import (
    ZocaloCallback,
)
from mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback import (
    GridscanISPyBCallback,
)
from mx_bluesky.common.external_interaction.callbacks.xray_centre.nexus_callback import (
    GridscanNexusFileCallback,
)
from mx_bluesky.common.external_interaction.ispyb.data_model import (
    DataCollectionGroupInfo,
)
from mx_bluesky.common.external_interaction.ispyb.ispyb_store import (
    IspybIds,
    StoreInIspyb,
)
from mx_bluesky.common.parameters.constants import (
    DocDescriptorNames,
    EnvironmentConstants,
    PlanNameConstants,
)
from mx_bluesky.common.parameters.gridscan import SpecifiedThreeDGridScan
from mx_bluesky.common.plans.common_flyscan_xray_centre_plan import (
    FlyScanEssentialDevices,
)
from tests.conftest import raw_params_from_file


@pytest.fixture
async def RE():
    RE = RunEngine(call_returns_result=True)
    # make sure the event loop is thoroughly up and running before we try to create
    # any ophyd_async devices which might need it
    timeout = time.monotonic() + 1
    while not RE.loop.is_running():
        await asyncio.sleep(0)
        if time.monotonic() > timeout:
            raise TimeoutError("This really shouldn't happen but just in case...")
    yield RE
    # RunEngine creates its own loop if we did not supply it, we must terminate it
    RE.loop.call_soon_threadsafe(RE.loop.stop)


MOCK_DAQ_CONFIG_PATH = "tests/devices/unit_tests/test_daq_configuration"
mock_paths = [
    ("DAQ_CONFIGURATION_PATH", MOCK_DAQ_CONFIG_PATH),
    ("ZOOM_PARAMS_FILE", "tests/devices/unit_tests/test_jCameraManZoomLevels.xml"),
    ("DISPLAY_CONFIG", "tests/devices/unit_tests/test_display.configuration"),
    ("LOOK_UPTABLE_DIR", "tests/devices/i10/lookupTables/"),
]
mock_attributes_table = {
    "i03": mock_paths,
    "i10": mock_paths,
    "i04": mock_paths,
    "i24": mock_paths,
}

BASIC_PRE_SETUP_DOC = {
    "undulator-current_gap": 0,
    "synchrotron-synchrotron_mode": SynchrotronMode.USER,
    "s4_slit_gaps-xgap": 0,
    "s4_slit_gaps-ygap": 0,
    "smargon-x": 10.0,
    "smargon-y": 20.0,
    "smargon-z": 30.0,
}

BASIC_POST_SETUP_DOC = {
    "aperture_scatterguard-selected_aperture": ApertureValue.OUT_OF_BEAM,
    "aperture_scatterguard-radius": None,
    "aperture_scatterguard-aperture-x": 15,
    "aperture_scatterguard-aperture-y": 16,
    "aperture_scatterguard-aperture-z": 2,
    "aperture_scatterguard-scatterguard-x": 18,
    "aperture_scatterguard-scatterguard-y": 19,
    "attenuator-actual_transmission": 0,
    "flux-flux_reading": 10,
    "dcm-energy_in_kev": 11.105,
}


def assert_event(mock_call, expected):
    actual = mock_call.args[0]
    if "data" in actual:
        actual = actual["data"]
    for k, v in expected.items():
        assert actual[k] == v, f"Mismatch in key {k}, {actual} <=> {expected}"


def mock_beamline_module_filepaths(bl_name, bl_module):
    if mock_attributes := mock_attributes_table.get(bl_name):
        [bl_module.__setattr__(attr[0], attr[1]) for attr in mock_attributes]
        beamline_parameters.BEAMLINE_PARAMETER_PATHS[bl_name] = (
            "tests/test_data/i04_beamlineParameters"
        )


def create_gridscan_callbacks() -> tuple[
    GridscanNexusFileCallback, GridscanISPyBCallback
]:
    return (
        GridscanNexusFileCallback(param_type=SpecifiedThreeDGridScan),
        GridscanISPyBCallback(
            param_type=SpecifiedThreeDGridScan,
            emit=ZocaloCallback(
                PlanNameConstants.DO_FGS, EnvironmentConstants.ZOCALO_ENV
            ),
        ),
    )


@pytest.fixture
def mock_subscriptions(test_fgs_params):
    with (
        patch(
            "mx_bluesky.common.external_interaction.callbacks.common.zocalo_callback.ZocaloTrigger",
            modified_interactor_mock,
        ),
        patch(
            "mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback.StoreInIspyb.append_to_comment"
        ),
        patch(
            "mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback.StoreInIspyb.begin_deposition",
            new=MagicMock(
                return_value=IspybIds(
                    data_collection_ids=(0, 0), data_collection_group_id=0
                )
            ),
        ),
        patch(
            "mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback.StoreInIspyb.update_deposition",
            new=MagicMock(
                return_value=IspybIds(
                    data_collection_ids=(0, 0),
                    data_collection_group_id=0,
                    grid_ids=(0, 0),
                )
            ),
        ),
    ):
        nexus_callback, ispyb_callback = create_gridscan_callbacks()
        ispyb_callback.ispyb = MagicMock(spec=StoreInIspyb)

    return (nexus_callback, ispyb_callback)


@pytest.fixture
def RE_with_subs(
    RE: RunEngine,
    mock_subscriptions: tuple[GridscanNexusFileCallback | GridscanISPyBCallback],
):
    for cb in list(mock_subscriptions):
        RE.subscribe(cb)
    yield RE, mock_subscriptions


@pytest.fixture
def test_fgs_params():
    return SpecifiedThreeDGridScan(
        **raw_params_from_file(
            "tests/test_data/parameter_json_files/good_test_parameters.json"
        )
    )


def mock_zocalo_trigger(zocalo: ZocaloResults, result):
    @AsyncStatus.wrap
    async def mock_complete(results):
        await zocalo._put_results(results, {"dcid": 0, "dcgid": 0})

    zocalo.trigger = MagicMock(side_effect=partial(mock_complete, result))


def modified_interactor_mock(assign_run_end: Callable | None = None):
    mock = MagicMock(spec=ZocaloTrigger)
    if assign_run_end:
        mock.run_end = assign_run_end
    return mock


def modified_store_grid_scan_mock(*args, dcids=(0, 0), dcgid=0, **kwargs):
    mock = MagicMock(spec=StoreInIspyb)
    mock.begin_deposition.return_value = IspybIds(
        data_collection_ids=dcids, data_collection_group_id=dcgid
    )
    mock.update_deposition.return_value = IspybIds(
        data_collection_ids=dcids, data_collection_group_id=dcgid, grid_ids=(0, 0)
    )
    return mock


def make_event_doc(data, descriptor="abc123") -> Event:
    return {
        "time": 0,
        "timestamps": {"a": 0},
        "seq_num": 0,
        "uid": "not so random uid",
        "descriptor": descriptor,
        "data": data,
    }


def run_generic_ispyb_handler_setup(
    ispyb_handler: GridscanISPyBCallback,
    params: SpecifiedThreeDGridScan,
):
    """This is useful when testing 'run_gridscan_and_move(...)' because this stuff
    happens at the start of the outer plan."""

    ispyb_handler.active = True
    ispyb_handler.activity_gated_start(
        {
            "subplan_name": PlanNameConstants.GRIDSCAN_OUTER,
            "mx_bluesky_parameters": params.model_dump_json(),
        }  # type: ignore
    )
    ispyb_handler.activity_gated_descriptor(
        {"uid": "123abc", "name": DocDescriptorNames.HARDWARE_READ_PRE}  # type: ignore
    )
    ispyb_handler.activity_gated_event(
        make_event_doc(
            BASIC_PRE_SETUP_DOC,
            descriptor="123abc",
        )
    )
    ispyb_handler.activity_gated_descriptor(
        {"uid": "abc123", "name": DocDescriptorNames.HARDWARE_READ_DURING}  # type: ignore
    )
    ispyb_handler.activity_gated_event(
        make_event_doc(
            BASIC_POST_SETUP_DOC,
            descriptor="abc123",
        )
    )


@pytest.fixture
async def zebra_fast_grid_scan():
    zebra_fast_grid_scan = i03.zebra_fast_grid_scan(connect_immediately=True, mock=True)
    set_mock_value(zebra_fast_grid_scan.scan_invalid, False)
    set_mock_value(zebra_fast_grid_scan.position_counter, 0)
    return zebra_fast_grid_scan


@pytest.fixture
async def fake_fgs_composite(
    smargon: Smargon,
    test_fgs_params: SpecifiedThreeDGridScan,
    RE: RunEngine,
    done_status,
    attenuator,
    xbpm_feedback,
    synchrotron,
    aperture_scatterguard,
    zocalo,
    panda,
    backlight,
):
    fake_composite = FlyScanEssentialDevices(
        # We don't use the eiger fixture here because .unstage() is used in some tests
        eiger=i03.eiger(connect_immediately=True, mock=True),
        smargon=smargon,
        synchrotron=synchrotron,
        zocalo=zocalo,
    )

    fake_composite.eiger.stage = MagicMock(return_value=done_status)
    # unstage should be mocked on a per-test basis because several rely on unstage
    fake_composite.eiger.set_detector_parameters(test_fgs_params.detector_params)
    fake_composite.eiger.stop_odin_when_all_frames_collected = MagicMock()
    fake_composite.eiger.odin.check_and_wait_for_odin_state = lambda timeout: True

    test_result = {
        "centre_of_mass": [6, 6, 6],
        "max_voxel": [5, 5, 5],
        "max_count": 123456,
        "n_voxels": 321,
        "total_count": 999999,
        "bounding_box": [[3, 3, 3], [9, 9, 9]],
    }

    @AsyncStatus.wrap
    async def mock_complete(result):
        await fake_composite.zocalo._put_results([result], {"dcid": 0, "dcgid": 0})

    fake_composite.zocalo.trigger = MagicMock(
        side_effect=partial(mock_complete, test_result)
    )  # type: ignore
    fake_composite.zocalo.timeout_s = 3
    set_mock_value(fake_composite.smargon.x.max_velocity, 10)

    return fake_composite


@pytest.fixture
def dummy_rotation_data_collection_group_info():
    return DataCollectionGroupInfo(
        visit_string="cm31105-4",
        experiment_type="SAD",
        sample_id=364758,
    )
