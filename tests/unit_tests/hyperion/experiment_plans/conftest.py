from collections.abc import Callable
from functools import partial
from unittest.mock import MagicMock, patch

import pytest
from bluesky.utils import Msg
from dodal.devices.aperturescatterguard import ApertureScatterguard, ApertureValue
from dodal.devices.backlight import Backlight
from dodal.devices.detector.detector_motion import DetectorMotion
from dodal.devices.fast_grid_scan import ZebraFastGridScan
from dodal.devices.oav.oav_detector import OAVConfigParams
from dodal.devices.smargon import Smargon
from dodal.devices.synchrotron import SynchrotronMode
from dodal.devices.zocalo import ZocaloResults, ZocaloTrigger
from event_model import Event
from ophyd.sim import NullStatus
from ophyd_async.core import AsyncStatus, DeviceCollector, set_mock_value

from mx_bluesky.hyperion.experiment_plans.grid_detect_then_xray_centre_plan import (
    GridDetectThenXRayCentreComposite,
)
from mx_bluesky.hyperion.experiment_plans.robot_load_and_change_energy import (
    RobotLoadAndEnergyChangeComposite,
)
from mx_bluesky.hyperion.experiment_plans.robot_load_then_centre_plan import (
    RobotLoadThenCentreComposite,
)
from mx_bluesky.hyperion.external_interaction.callbacks.common.callback_util import (
    create_gridscan_callbacks,
)
from mx_bluesky.hyperion.external_interaction.callbacks.xray_centre.ispyb_callback import (
    GridscanISPyBCallback,
)
from mx_bluesky.hyperion.external_interaction.ispyb.ispyb_store import (
    IspybIds,
    StoreInIspyb,
)
from mx_bluesky.hyperion.parameters.constants import CONST
from mx_bluesky.hyperion.parameters.gridscan import ThreeDGridScan


def make_event_doc(data, descriptor="abc123") -> Event:
    return {
        "time": 0,
        "timestamps": {"a": 0},
        "seq_num": 0,
        "uid": "not so random uid",
        "descriptor": descriptor,
        "data": data,
    }


BASIC_PRE_SETUP_DOC = {
    "undulator-current_gap": 0,
    "synchrotron-synchrotron_mode": SynchrotronMode.USER,
    "s4_slit_gaps_xgap": 0,
    "s4_slit_gaps_ygap": 0,
    "smargon-x": 10.0,
    "smargon-y": 20.0,
    "smargon-z": 30.0,
}

BASIC_POST_SETUP_DOC = {
    "aperture_scatterguard-selected_aperture": ApertureValue.ROBOT_LOAD,
    "aperture_scatterguard-radius": None,
    "aperture_scatterguard-aperture-x": 15,
    "aperture_scatterguard-aperture-y": 16,
    "aperture_scatterguard-aperture-z": 2,
    "aperture_scatterguard-scatterguard-x": 18,
    "aperture_scatterguard-scatterguard-y": 19,
    "attenuator-actual_transmission": 0,
    "flux_flux_reading": 10,
    "dcm-energy_in_kev": 11.105,
}


@pytest.fixture
def grid_detect_devices(
    aperture_scatterguard: ApertureScatterguard,
    backlight: Backlight,
    detector_motion: DetectorMotion,
    smargon: Smargon,
) -> GridDetectThenXRayCentreComposite:
    return GridDetectThenXRayCentreComposite(
        aperture_scatterguard=aperture_scatterguard,
        attenuator=MagicMock(),
        backlight=backlight,
        detector_motion=detector_motion,
        eiger=MagicMock(),
        zebra_fast_grid_scan=MagicMock(),
        flux=MagicMock(),
        oav=MagicMock(),
        pin_tip_detection=MagicMock(),
        smargon=smargon,
        synchrotron=MagicMock(),
        s4_slit_gaps=MagicMock(),
        undulator=MagicMock(),
        xbpm_feedback=MagicMock(),
        zebra=MagicMock(),
        zocalo=MagicMock(),
        panda=MagicMock(),
        panda_fast_grid_scan=MagicMock(),
        dcm=MagicMock(),
        robot=MagicMock(),
        sample_shutter=MagicMock(),
    )


@pytest.fixture
def sim_run_engine_for_rotation(sim_run_engine):
    sim_run_engine.add_handler(
        "read",
        lambda msg: {"values": {"value": SynchrotronMode.USER}},
        "synchrotron-synchrotron_mode",
    )
    sim_run_engine.add_handler(
        "read",
        lambda msg: {"values": {"value": -1}},
        "synchrotron-top_up_start_countdown",
    )
    sim_run_engine.add_handler(
        "read", lambda msg: {"values": {"value": -1}}, "smargon_omega"
    )
    return sim_run_engine


def mock_zocalo_trigger(zocalo: ZocaloResults, result):
    @AsyncStatus.wrap
    async def mock_complete(results):
        await zocalo._put_results(results, {"dcid": 0, "dcgid": 0})

    zocalo.trigger = MagicMock(side_effect=partial(mock_complete, result))


def run_generic_ispyb_handler_setup(
    ispyb_handler: GridscanISPyBCallback,
    params: ThreeDGridScan,
):
    """This is useful when testing 'run_gridscan_and_move(...)' because this stuff
    happens at the start of the outer plan."""

    ispyb_handler.active = True
    ispyb_handler.activity_gated_start(
        {
            "subplan_name": CONST.PLAN.GRIDSCAN_OUTER,
            "hyperion_parameters": params.model_dump_json(),
        }  # type: ignore
    )
    ispyb_handler.activity_gated_descriptor(
        {"uid": "123abc", "name": CONST.DESCRIPTORS.HARDWARE_READ_PRE}  # type: ignore
    )
    ispyb_handler.activity_gated_event(
        make_event_doc(
            BASIC_PRE_SETUP_DOC,
            descriptor="123abc",
        )
    )
    ispyb_handler.activity_gated_descriptor(
        {"uid": "abc123", "name": CONST.DESCRIPTORS.HARDWARE_READ_DURING}  # type: ignore
    )
    ispyb_handler.activity_gated_event(
        make_event_doc(
            BASIC_POST_SETUP_DOC,
            descriptor="abc123",
        )
    )


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


@pytest.fixture
def mock_subscriptions(test_fgs_params):
    with (
        patch(
            "mx_bluesky.hyperion.external_interaction.callbacks.zocalo_callback.ZocaloTrigger",
            modified_interactor_mock,
        ),
        patch(
            "mx_bluesky.hyperion.external_interaction.callbacks.xray_centre.ispyb_callback.StoreInIspyb.append_to_comment"
        ),
        patch(
            "mx_bluesky.hyperion.external_interaction.callbacks.xray_centre.ispyb_callback.StoreInIspyb.begin_deposition",
            new=MagicMock(
                return_value=IspybIds(
                    data_collection_ids=(0, 0), data_collection_group_id=0
                )
            ),
        ),
        patch(
            "mx_bluesky.hyperion.external_interaction.callbacks.xray_centre.ispyb_callback.StoreInIspyb.update_deposition",
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


def fake_read(obj, initial_positions, _):
    initial_positions[obj] = 0
    yield Msg("null", obj)


@pytest.fixture
def simple_beamline(
    detector_motion, eiger, oav, smargon, synchrotron, test_config_files, dcm
):
    magic_mock = MagicMock(autospec=True)

    with DeviceCollector(mock=True):
        magic_mock.zocalo = ZocaloResults()
        magic_mock.zebra_fast_grid_scan = ZebraFastGridScan("preifx", "fake_fgs")

    magic_mock.oav = oav
    magic_mock.smargon = smargon
    magic_mock.detector_motion = detector_motion
    magic_mock.dcm = dcm
    magic_mock.synchrotron = synchrotron
    magic_mock.eiger = eiger
    oav.zoom_controller.frst.set("7.5x")
    oav.parameters = OAVConfigParams(
        test_config_files["zoom_params_file"], test_config_files["display_config"]
    )
    oav.parameters.update_on_zoom(7.5, 1024, 768)
    return magic_mock


@pytest.fixture
def robot_load_composite(
    smargon,
    dcm,
    robot,
    aperture_scatterguard,
    oav,
    webcam,
    thawer,
    lower_gonio,
    eiger,
    xbpm_feedback,
    attenuator,
    fast_grid_scan,
    undulator,
    undulator_dcm,
    s4_slit_gaps,
    vfm,
    mirror_voltages,
    backlight,
    detector_motion,
    flux,
    ophyd_pin_tip_detection,
    zocalo,
    synchrotron,
    sample_shutter,
    zebra,
    panda,
    panda_fast_grid_scan,
) -> RobotLoadThenCentreComposite:
    set_mock_value(dcm.energy_in_kev.user_readback, 11.105)
    smargon.stub_offsets.set = MagicMock(return_value=NullStatus())
    aperture_scatterguard.set = MagicMock(return_value=NullStatus())
    return RobotLoadThenCentreComposite(
        xbpm_feedback=xbpm_feedback,
        attenuator=attenuator,
        aperture_scatterguard=aperture_scatterguard,
        backlight=backlight,
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
        zebra=zebra,
        zocalo=zocalo,
        panda=panda,
        panda_fast_grid_scan=panda_fast_grid_scan,
        thawer=thawer,
        sample_shutter=sample_shutter,
        vfm=vfm,
        mirror_voltages=mirror_voltages,
        dcm=dcm,
        undulator_dcm=undulator_dcm,
        robot=robot,
        webcam=webcam,
        lower_gonio=lower_gonio,
    )


@pytest.fixture
def robot_load_and_energy_change_composite(
    smargon, dcm, robot, aperture_scatterguard, oav, webcam, thawer, lower_gonio, eiger
) -> RobotLoadAndEnergyChangeComposite:
    composite: RobotLoadAndEnergyChangeComposite = MagicMock()
    composite.smargon = smargon
    composite.dcm = dcm
    set_mock_value(composite.dcm.energy_in_kev.user_readback, 11.105)
    composite.robot = robot
    composite.aperture_scatterguard = aperture_scatterguard
    composite.smargon.stub_offsets.set = MagicMock(return_value=NullStatus())
    composite.aperture_scatterguard.set = MagicMock(return_value=NullStatus())
    composite.oav = oav
    composite.webcam = webcam
    composite.lower_gonio = lower_gonio
    composite.thawer = thawer
    composite.eiger = eiger
    return composite


def assert_event(mock_call, expected):
    actual = mock_call.args[0]
    if "data" in actual:
        actual = actual["data"]
    for k, v in expected.items():
        assert actual[k] == v, f"Mismatch in key {k}, {actual} <=> {expected}"
