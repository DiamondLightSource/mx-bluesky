import os
from collections.abc import Callable, Generator, Sequence
from functools import partial
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import ispyb.sqlalchemy
import numpy
import pytest
import pytest_asyncio
from dodal.beamlines import i03
from dodal.devices.aperturescatterguard import ApertureScatterguard
from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
from dodal.devices.backlight import Backlight
from dodal.devices.detector.detector_motion import DetectorMotion
from dodal.devices.eiger import EigerDetector
from dodal.devices.flux import Flux
from dodal.devices.i03 import Beamstop
from dodal.devices.i03.dcm import DCM
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.oav.pin_image_recognition import PinTipDetection
from dodal.devices.robot import BartRobot
from dodal.devices.s4_slit_gaps import S4SlitGaps
from dodal.devices.smargon import Smargon
from dodal.devices.synchrotron import Synchrotron, SynchrotronMode
from dodal.devices.undulator import Undulator
from dodal.devices.xbpm_feedback import XBPMFeedback
from dodal.devices.zebra.zebra import Zebra
from dodal.devices.zebra.zebra_controlled_shutter import ZebraShutter
from dodal.devices.zocalo import ZocaloResults
from ispyb.sqlalchemy import (
    BLSample,
    DataCollection,
    DataCollectionGroup,
    GridInfo,
    Position,
)
from ophyd.sim import NullStatus
from ophyd_async.core import AsyncStatus
from ophyd_async.testing import callback_on_mock_put, set_mock_value
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from workflows.recipe import RecipeWrapper

from mx_bluesky.common.external_interaction.ispyb.ispyb_store import StoreInIspyb
from mx_bluesky.common.utils.utils import convert_angstrom_to_eV
from mx_bluesky.hyperion.experiment_plans.grid_detect_then_xray_centre_plan import (
    GridDetectThenXRayCentreComposite,
)
from mx_bluesky.hyperion.experiment_plans.rotation_scan_plan import (
    RotationScanComposite,
)
from mx_bluesky.hyperion.parameters.device_composites import (
    HyperionFlyScanXRayCentreComposite,
)
from mx_bluesky.hyperion.parameters.gridscan import HyperionSpecifiedThreeDGridScan
from mx_bluesky.hyperion.parameters.rotation import MultiRotationScan

from ....conftest import (
    TEST_RESULT_MEDIUM,
    SimConstants,
    fake_read,
    pin_tip_edge_data,
    raw_params_from_file,
)


def get_current_datacollection_comment(Session: Callable, dcid: int) -> str:
    """Read the 'comments' field from the given datacollection id's ISPyB entry.
    Returns an empty string if the comment is not yet initialised.
    """
    try:
        with Session() as session:
            query = session.query(DataCollection).filter(
                DataCollection.dataCollectionId == dcid
            )
            current_comment: str = query.first().comments
    except Exception:
        current_comment = ""
    return current_comment


def get_datacollections(Session: Callable, dcg_id: int) -> Sequence[int]:
    with Session.begin() as session:  # type: ignore
        query = session.query(DataCollection.dataCollectionId).filter(
            DataCollection.dataCollectionGroupId == dcg_id
        )
        return [row[0] for row in query.all()]


def get_current_datacollection_attribute(
    Session: Callable, dcid: int, attr: str
) -> str:
    """Read the specified field 'attr' from the given datacollection id's ISPyB entry.
    Returns an empty string if the attribute is not found.
    """
    try:
        with Session() as session:
            query = session.query(DataCollection).filter(
                DataCollection.dataCollectionId == dcid
            )
            first_result = query.first()
            data: str = getattr(first_result, attr)
    except Exception:
        data = ""
    return data


def get_current_datacollection_grid_attribute(
    Session: Callable, grid_id: int, attr: str
) -> Any:
    with Session() as session:
        query = session.query(GridInfo).filter(GridInfo.gridInfoId == grid_id)
        first_result = query.first()
        return getattr(first_result, attr)


def get_current_position_attribute(
    Session: Callable, position_id: int, attr: str
) -> Any:
    with Session() as session:
        query = session.query(Position).filter(Position.positionId == position_id)
        first_result = query.first()
        if first_result is None:
            return None
        return getattr(first_result, attr)


def get_current_datacollectiongroup_attribute(
    Session: Callable, dcg_id: int, attr: str
):
    with Session() as session:
        query = session.query(DataCollectionGroup).filter(
            DataCollectionGroup.dataCollectionGroupId == dcg_id
        )
        first_result = query.first()
        return getattr(first_result, attr)


def get_blsample(Session: Callable, bl_sample_id: int) -> BLSample:
    with Session() as session:
        query = session.query(BLSample).filter(BLSample.blSampleId == bl_sample_id)
        return query.first()


@pytest.fixture
def sqlalchemy_sessionmaker(ispyb_config_path) -> sessionmaker:
    url = ispyb.sqlalchemy.url(ispyb_config_path)
    engine = create_engine(url, connect_args={"use_pure": True})
    return sessionmaker(engine)


@pytest.fixture
def fetch_comment(sqlalchemy_sessionmaker) -> Callable:
    return partial(get_current_datacollection_comment, sqlalchemy_sessionmaker)


@pytest.fixture
def fetch_datacollection_ids_for_group_id(
    sqlalchemy_sessionmaker,
) -> Callable[[int], Sequence]:
    return partial(get_datacollections, sqlalchemy_sessionmaker)


@pytest.fixture
def fetch_datacollection_attribute(sqlalchemy_sessionmaker) -> Callable:
    return partial(get_current_datacollection_attribute, sqlalchemy_sessionmaker)


@pytest.fixture
def fetch_datacollection_grid_attribute(sqlalchemy_sessionmaker) -> Callable:
    return partial(get_current_datacollection_grid_attribute, sqlalchemy_sessionmaker)


@pytest.fixture
def fetch_datacollection_position_attribute(sqlalchemy_sessionmaker) -> Callable:
    return partial(get_current_position_attribute, sqlalchemy_sessionmaker)


@pytest.fixture
def fetch_datacollectiongroup_attribute(sqlalchemy_sessionmaker) -> Callable:
    return partial(get_current_datacollectiongroup_attribute, sqlalchemy_sessionmaker)


@pytest.fixture
def fetch_blsample(sqlalchemy_sessionmaker) -> Callable[[int], BLSample]:
    return partial(get_blsample, sqlalchemy_sessionmaker)


@pytest.fixture
def dummy_params():
    dummy_params = HyperionSpecifiedThreeDGridScan(
        **raw_params_from_file(
            "tests/test_data/parameter_json_files/test_gridscan_param_defaults.json"
        )
    )
    dummy_params.visit = SimConstants.ST_VISIT
    dummy_params.sample_id = SimConstants.ST_SAMPLE_ID
    return dummy_params


@pytest.fixture
def dummy_ispyb(ispyb_config_path, dummy_params) -> StoreInIspyb:
    return StoreInIspyb(ispyb_config_path)


@pytest.fixture
def zocalo_env():
    os.environ["ZOCALO_CONFIG"] = os.environ.get(
        "ZOCALO_CONFIG", "/dls_sw/apps/zocalo/live/configuration.yaml"
    )


@pytest_asyncio.fixture
async def zocalo_for_fake_zocalo(zocalo_env) -> ZocaloResults:
    """
    This attempts to connect to a fake zocalo via rabbitmq
    """
    zd = ZocaloResults()
    zd.timeout_s = 10
    await zd.connect()
    return zd


@pytest.fixture
def zocalo_for_system_test() -> Generator[ZocaloResults, None, None]:
    zocalo = i03.zocalo(connect_immediately=True, mock=True)
    old_zocalo_trigger = zocalo.trigger
    zocalo.my_zocalo_result = TEST_RESULT_MEDIUM

    @AsyncStatus.wrap
    async def mock_zocalo_complete():
        fake_recipe_wrapper = MagicMock(spec=RecipeWrapper)
        fake_recipe_wrapper.recipe_step = {"parameters": {"dcid": 1234, "dcgid": 123}}
        message = {
            "results": zocalo.my_zocalo_result  # type: ignore
        }
        header = {}
        zocalo.my_callback(fake_recipe_wrapper, header, message)  # type: ignore
        await old_zocalo_trigger()

    def mock_worfklow_subscribe(transport, channel, callback, **kwargs):
        if channel == "xrc.i03":
            zocalo.my_callback = callback

    with (
        patch("dodal.devices.zocalo.zocalo_results.workflows") as workflows,
        patch("dodal.devices.zocalo.zocalo_results._get_zocalo_connection"),
    ):
        workflows.recipe.wrap_subscribe.side_effect = mock_worfklow_subscribe
        with patch.object(zocalo, "trigger", side_effect=mock_zocalo_complete):
            yield zocalo


@pytest.fixture
def grid_detect_then_xray_centre_composite(
    fast_grid_scan,
    backlight,
    beamstop_i03,
    smargon,
    undulator_for_system_test,
    synchrotron,
    s4_slit_gaps,
    attenuator,
    xbpm_feedback,
    detector_motion,
    zocalo_for_system_test,
    aperture_scatterguard,
    zebra,
    eiger,
    robot,
    oav_for_system_test,
    dcm,
    flux,
    ophyd_pin_tip_detection,
    sample_shutter,
    panda,
    panda_fast_grid_scan,
):
    composite = GridDetectThenXRayCentreComposite(
        zebra_fast_grid_scan=fast_grid_scan,
        pin_tip_detection=ophyd_pin_tip_detection,
        backlight=backlight,
        beamstop=beamstop_i03,
        panda_fast_grid_scan=panda_fast_grid_scan,
        smargon=smargon,
        undulator=undulator_for_system_test,
        synchrotron=synchrotron,
        s4_slit_gaps=s4_slit_gaps,
        attenuator=attenuator,
        xbpm_feedback=xbpm_feedback,
        detector_motion=detector_motion,
        zocalo=zocalo_for_system_test,
        aperture_scatterguard=aperture_scatterguard,
        zebra=zebra,
        eiger=eiger,
        panda=panda,
        robot=robot,
        oav=oav_for_system_test,
        dcm=dcm,
        flux=flux,
        sample_shutter=sample_shutter,
    )

    @AsyncStatus.wrap
    async def mock_pin_tip_detect():
        tip_x_px, tip_y_px, top_edge_array, bottom_edge_array = pin_tip_edge_data()
        set_mock_value(
            ophyd_pin_tip_detection.triggered_top_edge,
            top_edge_array,
        )

        set_mock_value(
            ophyd_pin_tip_detection.triggered_bottom_edge,
            bottom_edge_array,
        )
        set_mock_value(
            zocalo_for_system_test.bounding_box,
            numpy.array([[10, 10, 10]], dtype=numpy.uint64),
        )
        set_mock_value(
            ophyd_pin_tip_detection.triggered_tip, numpy.array([tip_x_px, tip_y_px])
        )

    with (
        patch.object(eiger, "wait_on_arming_if_started"),
        # xsize, ysize will always be wrong since computed as 0 before we get here
        # patch up load_microns_per_pixel connect to receive non-zero values
        patch.object(
            ophyd_pin_tip_detection, "trigger", side_effect=mock_pin_tip_detect
        ),
        patch.object(fast_grid_scan, "kickoff", return_value=NullStatus()),
        patch.object(fast_grid_scan, "complete", return_value=NullStatus()),
    ):
        yield composite


@pytest.fixture
def fgs_composite_for_fake_zocalo(
    hyperion_flyscan_xrc_composite: HyperionFlyScanXRayCentreComposite,
    zocalo_for_fake_zocalo: ZocaloResults,
    done_status: NullStatus,
) -> HyperionFlyScanXRayCentreComposite:
    set_mock_value(
        hyperion_flyscan_xrc_composite.aperture_scatterguard.aperture.z.user_setpoint, 2
    )
    hyperion_flyscan_xrc_composite.eiger.unstage = MagicMock(return_value=done_status)  # type: ignore
    hyperion_flyscan_xrc_composite.smargon.stub_offsets.set = MagicMock(
        return_value=done_status
    )  # type: ignore
    callback_on_mock_put(
        hyperion_flyscan_xrc_composite.zebra_fast_grid_scan.run_cmd,
        lambda *args, **kwargs: set_mock_value(
            hyperion_flyscan_xrc_composite.zebra_fast_grid_scan.status, 1
        ),
    )
    hyperion_flyscan_xrc_composite.zebra_fast_grid_scan.complete = MagicMock(
        return_value=NullStatus()
    )
    hyperion_flyscan_xrc_composite.zocalo = zocalo_for_fake_zocalo
    return hyperion_flyscan_xrc_composite


@pytest.fixture
def pin_tip_no_pin_found(ophyd_pin_tip_detection):
    @AsyncStatus.wrap
    async def no_pin_tip_found():
        set_mock_value(
            ophyd_pin_tip_detection.triggered_tip, PinTipDetection.INVALID_POSITION
        )

        set_mock_value(
            ophyd_pin_tip_detection.triggered_top_edge,
            numpy.array([]),
        )

        set_mock_value(
            ophyd_pin_tip_detection.triggered_bottom_edge,
            numpy.array([]),
        )

    with patch.object(ophyd_pin_tip_detection, "trigger", side_effect=no_pin_tip_found):
        yield ophyd_pin_tip_detection


@pytest.fixture
def params_for_rotation_scan(
    test_rotation_params: MultiRotationScan,
) -> MultiRotationScan:
    test_rotation_params.rotation_increment_deg = 0.27
    test_rotation_params.exposure_time_s = 0.023
    test_rotation_params.detector_params.expected_energy_ev = 0.71
    test_rotation_params.visit = SimConstants.ST_VISIT
    test_rotation_params.sample_id = SimConstants.ST_SAMPLE_ID
    return test_rotation_params


@pytest.fixture
def composite_for_rotation_scan(
    beamstop_i03: Beamstop,
    eiger: EigerDetector,
    smargon: Smargon,
    zebra: Zebra,
    detector_motion: DetectorMotion,
    backlight: Backlight,
    attenuator: BinaryFilterAttenuator,
    flux: Flux,
    undulator_for_system_test: Undulator,
    aperture_scatterguard: ApertureScatterguard,
    synchrotron: Synchrotron,
    s4_slit_gaps: S4SlitGaps,
    dcm: DCM,
    robot: BartRobot,
    oav_for_system_test: OAV,
    sample_shutter: ZebraShutter,
    xbpm_feedback: XBPMFeedback,
):
    set_mock_value(smargon.omega.max_velocity, 131)
    oav_for_system_test.zoom_controller.level.describe = AsyncMock(
        return_value={"level": {"choices": ["1.0x", "5.0x", "7.5x"]}}
    )

    fake_create_rotation_devices = RotationScanComposite(
        attenuator=attenuator,
        backlight=backlight,
        beamstop=beamstop_i03,
        dcm=dcm,
        detector_motion=detector_motion,
        eiger=eiger,
        flux=flux,
        smargon=smargon,
        undulator=undulator_for_system_test,
        aperture_scatterguard=aperture_scatterguard,
        synchrotron=synchrotron,
        s4_slit_gaps=s4_slit_gaps,
        zebra=zebra,
        robot=robot,
        oav=oav_for_system_test,
        sample_shutter=sample_shutter,
        xbpm_feedback=xbpm_feedback,
    )

    energy_ev = convert_angstrom_to_eV(0.71)
    set_mock_value(
        fake_create_rotation_devices.dcm.energy_in_kev.user_readback,
        energy_ev / 1000,  # pyright: ignore
    )
    set_mock_value(
        fake_create_rotation_devices.synchrotron.synchrotron_mode,
        SynchrotronMode.USER,
    )
    set_mock_value(
        fake_create_rotation_devices.synchrotron.top_up_start_countdown,
        -1,
    )
    set_mock_value(fake_create_rotation_devices.s4_slit_gaps.xgap.user_readback, 0.123)
    set_mock_value(fake_create_rotation_devices.s4_slit_gaps.ygap.user_readback, 0.234)

    with (
        patch("bluesky.preprocessors.__read_and_stash_a_motor", fake_read),
        patch("bluesky.plan_stubs.wait"),
    ):
        yield fake_create_rotation_devices
