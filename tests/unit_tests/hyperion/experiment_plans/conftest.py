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
from dodal.devices.i03.beamstop import Beamstop
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.oav.pin_image_recognition import PinTipDetection
from dodal.devices.robot import BartRobot
from dodal.devices.s4_slit_gaps import S4SlitGaps
from dodal.devices.smargon import Smargon
from dodal.devices.synchrotron import Synchrotron, SynchrotronMode
from dodal.devices.zocalo import ZocaloResults
from ophyd.sim import NullStatus
from ophyd_async.fastcs.panda import HDFPanda
from ophyd_async.testing import set_mock_value

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
from mx_bluesky.hyperion.external_interaction.callbacks.common.callback_util import (
    create_gridscan_callbacks,
)

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
    "aperture_scatterguard-selected_aperture": ApertureValue.ROBOT_LOAD,
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
def grid_detect_devices(
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
) -> GridDetectThenXRayCentreComposite:
    return GridDetectThenXRayCentreComposite(
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


def sim_fire_event_on_open_run(sim_run_engine: RunEngineSimulator, run_name: str):
    def fire_event(msg: Msg):
        try:
            sim_run_engine.fire_callback("start", msg.kwargs)
        except Exception as e:
            print(f"Exception is {e}")

    def msg_maches_run(msg: Msg):
        return msg.run == run_name

    sim_run_engine.add_handler("open_run", fire_event, msg_maches_run)
