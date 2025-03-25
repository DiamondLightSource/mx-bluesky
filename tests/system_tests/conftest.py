import os
import re
from collections.abc import Generator
from decimal import Decimal
from functools import partial
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import ClientResponse
from dodal.beamlines import i03
from dodal.devices.oav.oav_parameters import OAVConfig
from ophyd_async.core import AsyncStatus
from ophyd_async.testing import set_mock_value
from PIL import Image

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


@pytest.fixture(autouse=True, scope="session")
def ispyb_config_path() -> Generator[str, Any, Any]:
    ispyb_config_path = os.environ.get(
        "ISPYB_CONFIG_PATH", "/dls_sw/dasc/mariadb/credentials/ispyb-hyperion-dev.cfg"
    )
    with patch.dict(os.environ, {"ISPYB_CONFIG_PATH": ispyb_config_path}):
        yield ispyb_config_path


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
def oav_for_system_test(test_config_files, next_oav_system_test_image):
    parameters = OAVConfig(
        test_config_files["zoom_params_file"], test_config_files["display_config"]
    )
    oav = i03.oav(connect_immediately=True, mock=True, params=parameters)
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
            "dodal.devices.areadetector.plugins.MJPG.ClientSession.get", autospec=True
        ) as mock_get,
    ):
        mock_get.return_value.__aenter__.return_value = empty_response
        set_mock_value(oav.zoom_controller.level, "1.0x")
        zoom_levels_list = ["1.0x", "3.0x", "5.0x", "7.5x", "10.0x", "15.0x"]
        oav.zoom_controller._get_allowed_zoom_levels = AsyncMock(
            return_value=zoom_levels_list
        )
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
