from functools import partial
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from bluesky.simulators import RunEngineSimulator
from bluesky.utils import Msg
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
from dodal.devices.zocalo import ZocaloResults
from event_model import Event
from ophyd.sim import NullStatus
from ophyd_async.core import AsyncStatus
from ophyd_async.fastcs.panda import HDFPanda
from ophyd_async.testing import set_mock_value

from mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback import (
    GridscanISPyBCallback,
)
from mx_bluesky.common.external_interaction.ispyb.ispyb_store import (
    IspybIds,
    StoreInIspyb,
)
from mx_bluesky.common.xrc_result import XRayCentreResult
from mx_bluesky.hyperion.experiment_plans.grid_detect_then_xray_centre_plan import (
    GridDetectThenXRayCentreComposite,
)
from mx_bluesky.hyperion.experiment_plans.robot_load_and_change_energy import (
    RobotLoadAndEnergyChangeComposite,
)
from mx_bluesky.hyperion.experiment_plans.robot_load_then_centre_plan import (
    RobotLoadThenCentreComposite,
)
from mx_bluesky.hyperion.external_interaction.callbacks.__main__ import (
    create_gridscan_callbacks,
)
from mx_bluesky.hyperion.parameters.constants import CONST
from mx_bluesky.hyperion.parameters.gridscan import HyperionSpecifiedThreeDGridScan

FLYSCAN_RESULT_HIGH = XRayCentreResult(
    centre_of_mass_mm=np.array([0.1, 0.2, 0.3]),
    bounding_box_mm=(np.array([0.09, 0.19, 0.29]), np.array([0.11, 0.21, 0.31])),
    max_count=30,
    total_count=100,
)
FLYSCAN_RESULT_MED = XRayCentreResult(
    centre_of_mass_mm=np.array([0.4, 0.5, 0.6]),
    bounding_box_mm=(np.array([0.09, 0.19, 0.29]), np.array([0.11, 0.21, 0.31])),
    max_count=20,
    total_count=120,
)
FLYSCAN_RESULT_LOW = XRayCentreResult(
    centre_of_mass_mm=np.array([0.7, 0.8, 0.9]),
    bounding_box_mm=(np.array([0.09, 0.19, 0.29]), np.array([0.11, 0.21, 0.31])),
    max_count=10,
    total_count=140,
)


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


@pytest.fixture
async def grid_detect_devices(
    aperture_scatterguard: ApertureScatterguard,
    backlight: Backlight,
    beamstop_i03: Beamstop,
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
    undulator_dcm,
    dcm,
):
    yield GridDetectThenXRayCentreComposite(
        aperture_scatterguard=aperture_scatterguard,
        attenuator=attenuator,
        backlight=backlight,
        beamstop=beamstop_i03,
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
        panda=MagicMock(spec=HDFPanda),
        panda_fast_grid_scan=MagicMock(spec=PandAFastGridScan),
        dcm=dcm,
        robot=MagicMock(spec=BartRobot),
        sample_shutter=zebra_shutter,
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
    params: HyperionSpecifiedThreeDGridScan,
):
    """This is useful when testing 'run_gridscan_and_move(...)' because this stuff
    happens at the start of the outer plan."""

    ispyb_handler.active = True
    ispyb_handler.activity_gated_start(
        {
            "subplan_name": CONST.PLAN.GRIDSCAN_OUTER,
            "mx_bluesky_parameters": params.model_dump_json(),
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
def mock_subscriptions():
    with (
        patch(
            "mx_bluesky.common.external_interaction.callbacks.common.zocalo_callback.ZocaloTrigger",
            autospec=True,
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


def fake_read(obj, initial_positions, _):
    initial_positions[obj] = 0
    yield Msg("null", obj)


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
    beamstop_i03,
    fast_grid_scan,
    undulator,
    undulator_dcm,
    s4_slit_gaps,
    vfm,
    mirror_voltages,
    backlight,
    detector_motion,
    flux,
    pin_tip_detection_with_found_pin,
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
    set_mock_value(smargon.omega.max_velocity, 131)
    return RobotLoadThenCentreComposite(
        xbpm_feedback=xbpm_feedback,
        attenuator=attenuator,
        aperture_scatterguard=aperture_scatterguard,
        backlight=backlight,
        beamstop=beamstop_i03,
        detector_motion=detector_motion,
        eiger=eiger,
        zebra_fast_grid_scan=fast_grid_scan,
        flux=flux,
        oav=oav,
        pin_tip_detection=pin_tip_detection_with_found_pin,
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
    smargon,
    dcm,
    robot,
    aperture_scatterguard,
    oav,
    webcam,
    thawer,
    lower_gonio,
    vfm,
    mirror_voltages,
    undulator_dcm,
    xbpm_feedback,
    attenuator,
    backlight,
) -> RobotLoadAndEnergyChangeComposite:
    composite = RobotLoadAndEnergyChangeComposite(
        vfm,
        mirror_voltages,
        dcm,
        undulator_dcm,
        xbpm_feedback,
        attenuator,
        robot,
        webcam,
        lower_gonio,
        thawer,
        oav,
        smargon,
        aperture_scatterguard,
        backlight,
    )
    composite.smargon.stub_offsets.set = MagicMock(return_value=NullStatus())
    composite.aperture_scatterguard.set = MagicMock(return_value=NullStatus())
    set_mock_value(composite.dcm.energy_in_kev.user_readback, 11.105)

    return composite


def sim_fire_event_on_open_run(sim_run_engine: RunEngineSimulator, run_name: str):
    def fire_event(msg: Msg):
        try:
            sim_run_engine.fire_callback("start", msg.kwargs)
        except Exception as e:
            print(f"Exception is {e}")

    def msg_maches_run(msg: Msg):
        return msg.run == run_name

    sim_run_engine.add_handler("open_run", fire_event, msg_maches_run)


@pytest.fixture
def grid_detection_callback_with_detected_grid():
    with patch(
        "mx_bluesky.hyperion.experiment_plans.grid_detect_then_xray_centre_plan.GridDetectionCallback",
        autospec=True,
    ) as callback:
        callback.return_value.get_grid_parameters.return_value = {
            "transmission_frac": 1.0,
            "exposure_time_s": 0,
            "x_start_um": 0,
            "y_start_um": 0,
            "y2_start_um": 0,
            "z_start_um": 0,
            "z2_start_um": 0,
            "x_steps": 10,
            "y_steps": 10,
            "z_steps": 10,
            "x_step_size_um": 0.1,
            "y_step_size_um": 0.1,
            "z_step_size_um": 0.1,
        }
        yield callback
