import asyncio
import pprint
import sys
import time
from collections.abc import Callable
from functools import partial
from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from _pytest.fixtures import FixtureRequest
from bluesky.run_engine import RunEngine
from dodal.beamlines import i03
from dodal.devices.aperturescatterguard import ApertureScatterguard, ApertureValue
from dodal.devices.backlight import Backlight
from dodal.devices.detector.detector_motion import DetectorMotion
from dodal.devices.eiger import EigerDetector
from dodal.devices.fast_grid_scan import PandAFastGridScan, ZebraFastGridScan
from dodal.devices.flux import Flux
from dodal.devices.i03 import Beamstop
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.oav.pin_image_recognition import PinTipDetection
from dodal.devices.robot import BartRobot
from dodal.devices.s4_slit_gaps import S4SlitGaps
from dodal.devices.smargon import Smargon
from dodal.devices.synchrotron import Synchrotron, SynchrotronMode
from dodal.devices.zocalo import ZocaloResults, ZocaloTrigger
from event_model.documents import Event
from ophyd_async.core import AsyncStatus, init_devices
from ophyd_async.fastcs.jungfrau import Jungfrau
from ophyd_async.fastcs.panda import HDFPanda
from ophyd_async.testing import callback_on_mock_put, set_mock_value

from mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan import (
    BeamlineSpecificFGSFeatures,
    FlyScanEssentialDevices,
)
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
from mx_bluesky.common.parameters.device_composites import (
    GridDetectThenXRayCentreComposite,
)
from mx_bluesky.common.parameters.gridscan import GridCommon, SpecifiedThreeDGridScan
from mx_bluesky.hyperion.parameters.device_composites import (
    HyperionGridDetectThenXRayCentreComposite,
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
    RE._th.join()


_ALLOWED_PYTEST_TASKS = {"async_finalizer", "async_setup", "async_teardown"}


def _error_and_kill_pending_tasks(
    loop: asyncio.AbstractEventLoop, test_name: str, test_passed: bool
) -> set[asyncio.Task]:
    """Cancels pending tasks in the event loop for a test. Raises an exception if
    the test hasn't already.

    Args:
        loop: The event loop to check for pending tasks.
        test_name: The name of the test.
        test_passed: Indicates whether the test passed.

    Returns:
        set[asyncio.Task]: The set of unfinished tasks that were cancelled.

    Raises:
        RuntimeError: If there are unfinished tasks and the test didn't fail.
    """
    unfinished_tasks = {
        task
        for task in asyncio.all_tasks(loop)
        if (coro := task.get_coro()) is not None
        and hasattr(coro, "__name__")
        and coro.__name__ not in _ALLOWED_PYTEST_TASKS
        and not task.done()
    }
    for task in unfinished_tasks:
        task.cancel()

    # We only raise an exception here if the test didn't fail anyway.
    # If it did then it makes sense that there's some tasks we need to cancel,
    # but an exception will already have been raised.
    if unfinished_tasks and test_passed:
        raise RuntimeError(
            f"Not all tasks closed during test {test_name}:\n"
            f"{pprint.pformat(unfinished_tasks, width=88)}"
        )

    return unfinished_tasks


@pytest.fixture(autouse=True, scope="function")
async def fail_test_on_unclosed_tasks(request: FixtureRequest):
    """
    Used on every test to ensure failure if there are pending tasks
    by the end of the test.
    """

    fail_count = request.session.testsfailed
    loop = asyncio.get_running_loop()

    loop.set_debug(True)

    request.addfinalizer(
        lambda: _error_and_kill_pending_tasks(
            loop, request.node.name, request.session.testsfailed == fail_count
        )
    )


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
def use_beamline_t01():
    """Beamline t01 is a beamline for unit tests that just contains a baton, so that
    loading the beamline context does not require importing lots of modules and instantiating
    many devices"""
    with patch.dict("os.environ", {"BEAMLINE": "t01"}):
        import tests.unit_tests.t01

        with patch.dict(sys.modules, {"dodal.beamlines.t01": tests.unit_tests.t01}):
            yield


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
def test_fgs_params(tmp_path):
    return SpecifiedThreeDGridScan(
        **raw_params_from_file(
            "tests/test_data/parameter_json_files/good_test_parameters.json", tmp_path
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
        "sample_id": 12345,
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


@pytest.fixture
def beamline_specific(
    zebra_fast_grid_scan: ZebraFastGridScan,
) -> BeamlineSpecificFGSFeatures:
    return BeamlineSpecificFGSFeatures(
        setup_trigger_plan=MagicMock(),
        tidy_plan=MagicMock(),
        set_flyscan_params_plan=MagicMock(),
        fgs_motors=zebra_fast_grid_scan,
        read_pre_flyscan_plan=MagicMock(),
        read_during_collection_plan=MagicMock(),
        get_xrc_results_from_zocalo=False,
    )


@pytest.fixture
def test_full_grid_scan_params(tmp_path):
    params = raw_params_from_file(
        "tests/test_data/parameter_json_files/good_test_grid_with_edge_detect_parameters.json",
        tmp_path,
    )
    return GridCommon(**params)


@pytest.fixture
async def grid_detect_xrc_devices(
    aperture_scatterguard: ApertureScatterguard,
    backlight: Backlight,
    beamstop_phase1: Beamstop,
    detector_motion: DetectorMotion,
    eiger: EigerDetector,
    smargon: Smargon,
    oav: OAV,
    ophyd_pin_tip_detection: PinTipDetection,
    zocalo: ZocaloResults,
    synchrotron: Synchrotron,
    fast_grid_scan: ZebraFastGridScan,
    s4_slit_gaps: S4SlitGaps,
    flux: Flux,
    zebra,
    zebra_shutter,
    xbpm_feedback,
    attenuator,
    undulator,
    dcm,
):
    yield GridDetectThenXRayCentreComposite(
        aperture_scatterguard=aperture_scatterguard,
        attenuator=attenuator,
        backlight=backlight,
        beamstop=beamstop_phase1,
        detector_motion=detector_motion,
        eiger=eiger,
        zebra_fast_grid_scan=fast_grid_scan,
        flux=flux,
        oav=oav,
        pin_tip_detection=ophyd_pin_tip_detection,
        smargon=smargon,
        synchrotron=synchrotron,
        s4_slit_gaps=s4_slit_gaps,
        undulator=undulator,
        xbpm_feedback=xbpm_feedback,
        zebra=zebra,
        zocalo=zocalo,
        dcm=dcm,
        robot=MagicMock(spec=BartRobot),
        sample_shutter=zebra_shutter,
    )


@pytest.fixture
async def hyperion_grid_detect_xrc_devices(grid_detect_xrc_devices):
    composite = cast(HyperionGridDetectThenXRayCentreComposite, grid_detect_xrc_devices)
    composite.panda = MagicMock(spec=HDFPanda)
    composite.panda_fast_grid_scan = MagicMock(spec=PandAFastGridScan)
    return composite


# See https://github.com/DiamondLightSource/dodal/issues/1455
@pytest.fixture
def jungfrau(RE: RunEngine):
    """The extra logic here prevents exceptions during data collection unit tests"""

    with init_devices(mock=True):
        detector = Jungfrau("prefix", MagicMock(), "", "", 4, "jungfrau")

    def set_meta_filename_and_id(value, *args, **kwargs):
        set_mock_value(detector.odin.meta_file_name, value)
        set_mock_value(detector.odin.id, value)

    callback_on_mock_put(detector.odin.file_name, set_meta_filename_and_id)

    detector._writer._path_provider.return_value.filename = "filename.h5"  # type: ignore

    set_mock_value(detector.odin.meta_active, "Active")
    set_mock_value(detector.odin.capture_rbv, "Capturing")
    set_mock_value(detector.odin.meta_writing, "Writing")
    return detector
