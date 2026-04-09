import os
import re
from collections.abc import Generator
from decimal import Decimal
from functools import partial
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import ClientResponse
from bluesky.simulators import RunEngineSimulator
from daq_config_server import ConfigClient
from dodal.beamlines import i03
from dodal.beamlines.i03 import DISPLAY_CONFIG, ZOOM_PARAMS_FILE
from dodal.common.beamlines import beamline_utils
from dodal.common.beamlines.beamline_utils import (
    set_config_client,
)
from dodal.devices.aperturescatterguard import (
    ApertureScatterguard,
)
from dodal.devices.attenuator.attenuator import (
    BinaryFilterAttenuator,
)
from dodal.devices.backlight import Backlight
from dodal.devices.beamlines.i03 import Beamstop, BeamstopPositions
from dodal.devices.beamlines.i03.dcm import DCM
from dodal.devices.beamlines.i03.undulator_dcm import UndulatorDCM
from dodal.devices.beamsize.beamsize import BeamsizeBase
from dodal.devices.detector.detector_motion import DetectorMotion
from dodal.devices.eiger import EigerDetector
from dodal.devices.flux import Flux
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.oav.oav_parameters import OAVConfigBeamCentre, OAVParameters
from dodal.devices.robot import BartRobot
from dodal.devices.s4_slit_gaps import S4SlitGaps
from dodal.devices.smargon import Smargon
from dodal.devices.synchrotron import Synchrotron
from dodal.devices.thawer import Thawer
from dodal.devices.undulator import UndulatorInKeV
from dodal.devices.xbpm_feedback import XBPMFeedback
from dodal.devices.zebra.zebra import Zebra
from dodal.devices.zebra.zebra_controlled_shutter import ZebraShutter
from ophyd_async.core import (
    AsyncStatus,
    completed_status,
    set_mock_value,
)
from PIL import Image

from mx_bluesky.hyperion.experiment_plans.rotation_scan_plan import (
    RotationScanComposite,
)
from tests.conftest import set_up_dcm

# Map all the case-sensitive column names from their normalised versions
DATA_COLLECTION_COLUMN_MAP = {
    s.lower(): s
    for s in [
        "dataCollectionId",
        "BLSAMPLEID",
        "SESSIONID",
        "experimenttype",
        "dataCollectionNumber",
        "startTime",
        "endTime",
        "runStatus",
        "axisStart",
        "axisEnd",
        "axisRange",
        "overlap",
        "numberOfImages",
        "startImageNumber",
        "numberOfPasses",
        "exposureTime",
        "imageDirectory",
        "imagePrefix",
        "imageSuffix",
        "imageContainerSubPath",
        "fileTemplate",
        "wavelength",
        "resolution",
        "detectorDistance",
        "xBeam",
        "yBeam",
        "comments",
        "printableForReport",
        "CRYSTALCLASS",
        "slitGapVertical",
        "slitGapHorizontal",
        "transmission",
        "synchrotronMode",
        "xtalSnapshotFullPath1",
        "xtalSnapshotFullPath2",
        "xtalSnapshotFullPath3",
        "xtalSnapshotFullPath4",
        "rotationAxis",
        "phiStart",
        "kappaStart",
        "omegaStart",
        "chiStart",
        "resolutionAtCorner",
        "detector2Theta",
        "DETECTORMODE",
        "undulatorGap1",
        "undulatorGap2",
        "undulatorGap3",
        "beamSizeAtSampleX",
        "beamSizeAtSampleY",
        "centeringMethod",
        "averageTemperature",
        "ACTUALSAMPLEBARCODE",
        "ACTUALSAMPLESLOTINCONTAINER",
        "ACTUALCONTAINERBARCODE",
        "ACTUALCONTAINERSLOTINSC",
        "actualCenteringPosition",
        "beamShape",
        "dataCollectionGroupId",
        "POSITIONID",
        "detectorId",
        "FOCALSPOTSIZEATSAMPLEX",
        "POLARISATION",
        "FOCALSPOTSIZEATSAMPLEY",
        "APERTUREID",
        "screeningOrigId",
        "flux",
        "strategySubWedgeOrigId",
        "blSubSampleId",
        "processedDataFile",
        "datFullPath",
        "magnification",
        "totalAbsorbedDose",
        "binning",
        "particleDiameter",
        "boxSize",
        "minResolution",
        "minDefocus",
        "maxDefocus",
        "defocusStepSize",
        "amountAstigmatism",
        "extractSize",
        "bgRadius",
        "voltage",
        "objAperture",
        "c1aperture",
        "c2aperture",
        "c3aperture",
        "c1lens",
        "c2lens",
        "c3lens",
        "startPositionId",
        "endPositionId",
        "flux",
        "bestWilsonPlotPath",
        "totalExposedDose",
        "nominalMagnification",
        "nominalDefocus",
        "imageSizeX",
        "imageSizeY",
        "pixelSizeOnImage",
        "phasePlate",
        "dataCollectionPlanId",
    ]
}

LOCAL_CONFIG_SERVER_URL = "http://0.0.0.0:8555"


def _system_test_env_error_message(env_var: str):
    return RuntimeError(
        f"Environment variable {env_var} is not set, please ensure that the system test container "
        f"images are running and the system tests are invoked via tox -e localsystemtests - see "
        f"https://gitlab.diamond.ac.uk/MX-GDA/hyperion-system-testing for details."
    )


@pytest.fixture(autouse=True, scope="session")
def ispyb_config_path() -> Generator[str, Any, Any]:
    ispyb_config_path = os.environ.get("ISPYB_CONFIG_PATH")
    if ispyb_config_path is None:
        raise _system_test_env_error_message("ISPYB_CONFIG_PATH")
    yield ispyb_config_path


@pytest.fixture
def zocalo_env():
    zocalo_config = os.environ.get("ZOCALO_CONFIG")
    if zocalo_config is None:
        raise _system_test_env_error_message("ZOCALO_CONFIG")
    yield zocalo_config


@pytest.fixture
def undulator_for_system_test(undulator):
    set_mock_value(undulator.current_gap, 1.11)
    return undulator


@pytest.fixture
def next_oav_system_test_image():
    return MagicMock(
        return_value="tests/test_data/test_images/generate_snapshot_input.png"
    )


@pytest.fixture
def oav_for_system_test(config_client: ConfigClient, next_oav_system_test_image):
    parameters = OAVConfigBeamCentre(
        ZOOM_PARAMS_FILE,
        DISPLAY_CONFIG,
        config_client,
    )
    oav = i03.oav.build(connect_immediately=True, mock=True, params=parameters)
    set_mock_value(oav.cam.array_size_x, 1024)
    set_mock_value(oav.cam.array_size_y, 768)

    # Grid snapshots
    set_mock_value(oav.grid_snapshot.x_size, 1024)
    set_mock_value(oav.grid_snapshot.y_size, 768)
    set_mock_value(oav.grid_snapshot.top_left_x, 50)
    set_mock_value(oav.grid_snapshot.top_left_y, 100)
    size_in_pixels = 0.1 * 1000 / 1.25
    set_mock_value(oav.grid_snapshot.box_width, size_in_pixels)

    # Rotation snapshots
    @AsyncStatus.wrap
    async def trigger_with_test_image(self):
        with Image.open(next_oav_system_test_image()) as image:
            await self.post_processing(image)

    oav.snapshot.trigger = MagicMock(
        side_effect=partial(trigger_with_test_image, oav.snapshot)
    )
    oav.grid_snapshot.trigger = MagicMock(
        side_effect=partial(trigger_with_test_image, oav.grid_snapshot)
    )

    empty_response = AsyncMock(spec=ClientResponse)
    empty_response.read.return_value = b""

    with (
        patch(
            "dodal.devices.areadetector.plugins.mjpg.ClientSession.get", autospec=True
        ) as mock_get,
    ):
        mock_get.return_value.__aenter__.return_value = empty_response
        set_mock_value(oav.zoom_controller.level, "1.0x")
        yield oav


def compare_actual_and_expected(
    id, expected_values, fetch_datacollection_attribute, column_map: dict | None = None
):
    results = "\n"
    for k, v in expected_values.items():
        actual = fetch_datacollection_attribute(
            id, column_map[k.lower()] if column_map else k
        )
        if isinstance(actual, Decimal):
            actual = float(actual)
        if isinstance(v, float):
            actual_v = actual == pytest.approx(v)
        elif isinstance(v, str) and v.startswith("regex:"):
            actual_v = re.match(v.removeprefix("regex:"), str(actual))  # type: ignore
        else:
            actual_v = actual == v
        if not actual_v:
            results += f"expected {k} {v} == {actual}\n"
    assert results == "\n", results


def compare_comment(
    fetch_datacollection_attribute, data_collection_id, expected_comment
):
    actual_comment = fetch_datacollection_attribute(
        data_collection_id, DATA_COLLECTION_COLUMN_MAP["comments"]
    )
    match = re.search(" Zocalo processing took", actual_comment)
    truncated_comment = actual_comment[: match.start()] if match else actual_comment
    assert truncated_comment == expected_comment


@pytest.fixture
def config_client():
    # Connects to real config server hosted locally
    # Test files are stored in the hyperion-system-tests repo under ./daq_config_server/config/
    # They have been mounted to match the paths in /dls_sw/i03/ so that the whitelist
    # and file converter map behave as expected with no mocking needed.
    # https://gitlab.diamond.ac.uk/MX-GDA/hyperion-system-testing/-/tree/add_daq_config_server/daq-config-server/config/?ref_type=heads
    return ConfigClient(url=LOCAL_CONFIG_SERVER_URL)


@pytest.fixture(autouse=True)
def patch_config_client():
    config_client = ConfigClient(LOCAL_CONFIG_SERVER_URL)
    set_config_client(config_client)


@pytest.fixture(autouse=True)
def patch_get_hyperion_feature_settings():
    path = "/dls_sw/i03/software/daq_configuration/domain/domain.properties"
    with patch(
        "mx_bluesky.hyperion.external_interaction.config_server.GDA_DOMAIN_PROPERTIES_PATH",
        str(path),
    ):
        yield


@pytest.fixture
def undulator_dcm(sim_run_engine, dcm, undulator) -> Generator[UndulatorDCM]:
    undulator_dcm: UndulatorDCM = i03.undulator_dcm.build(
        connect_immediately=True,
        mock=True,
        daq_configuration_path="/dls_sw/i03/software/daq_configuration/",
        dcm=dcm,
        undulator=undulator,
    )
    set_up_dcm(undulator_dcm.dcm_ref(), sim_run_engine)
    yield undulator_dcm


@pytest.fixture
def oav_parameters_for_rotation(config_client) -> OAVParameters:
    return OAVParameters(
        config_client,
        oav_config_json="/dls_sw/i03/software/daq_configuration/json/OAVCentring.json",
    )


@pytest.fixture()
def system_tests_rotation_devices(
    beamstop_phase1_for_system_test: Beamstop,
    eiger: EigerDetector,
    smargon: Smargon,
    zebra: Zebra,
    detector_motion: DetectorMotion,
    backlight: Backlight,
    attenuator: BinaryFilterAttenuator,
    flux: Flux,
    undulator: UndulatorInKeV,
    aperture_scatterguard: ApertureScatterguard,
    synchrotron: Synchrotron,
    s4_slit_gaps: S4SlitGaps,
    dcm: DCM,
    robot: BartRobot,
    oav_for_system_test: OAV,
    sample_shutter: ZebraShutter,
    xbpm_feedback: XBPMFeedback,
    thawer: Thawer,
    beamsize: BeamsizeBase,
):
    set_mock_value(smargon.omega.max_velocity, 131)
    undulator.set = MagicMock(side_effect=lambda _: completed_status())
    return RotationScanComposite(
        attenuator=attenuator,
        backlight=backlight,
        beamsize=beamsize,
        beamstop=beamstop_phase1_for_system_test,
        dcm=dcm,
        detector_motion=detector_motion,
        eiger=eiger,
        flux=flux,
        gonio=smargon,
        undulator=undulator,
        aperture_scatterguard=aperture_scatterguard,
        synchrotron=synchrotron,
        s4_slit_gaps=s4_slit_gaps,
        zebra=zebra,
        robot=robot,
        oav=oav_for_system_test,
        sample_shutter=sample_shutter,
        xbpm_feedback=xbpm_feedback,
        thawer=thawer,
    )


@pytest.fixture
def beamstop_phase1_for_system_test(
    sim_run_engine: RunEngineSimulator,
) -> Generator[Beamstop, Any, Any]:
    beamstop = i03.beamstop.build(connect_immediately=True, mock=True)

    set_mock_value(beamstop.x_mm.user_readback, 1.52)
    set_mock_value(beamstop.y_mm.user_readback, 44.78)
    set_mock_value(beamstop.z_mm.user_readback, 30.0)

    # sim_run_engine.add_read_handler_for(
    #     beamstop.selected_pos, BeamstopPositions.DATA_COLLECTION
    # )
    # Can uncomment and remove below when https://github.com/bluesky/bluesky/issues/1906 is fixed
    def locate_beamstop(_):
        return {"readback": BeamstopPositions.DATA_COLLECTION}

    sim_run_engine.add_handler("locate", locate_beamstop, beamstop.selected_pos.name)

    yield beamstop
    beamline_utils.clear_devices()
