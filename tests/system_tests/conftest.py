import re
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from dodal.beamlines import i03
from dodal.devices.oav.oav_parameters import OAVConfig
from ophyd_async.core import AsyncStatus, set_mock_value
from requests import Response

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


@pytest.fixture
def undulator_for_system_test(undulator):
    set_mock_value(undulator.current_gap, 1.11)
    return undulator


@pytest.fixture
def oav_for_system_test(test_config_files):
    parameters = OAVConfig(
        test_config_files["zoom_params_file"], test_config_files["display_config"]
    )
    oav = i03.oav(fake_with_ophyd_sim=True, params=parameters)
    set_mock_value(oav.cam.array_size_x, 1024)
    set_mock_value(oav.cam.array_size_y, 768)

    # Grid snapshots
    set_mock_value(oav.grid_snapshot.x_size, 1024)
    set_mock_value(oav.grid_snapshot.y_size, 768)
    set_mock_value(oav.grid_snapshot.top_left_x, 50)
    set_mock_value(oav.grid_snapshot.top_left_y, 100)
    size_in_pixels = int(0.1 * 1000 / 1.25)
    set_mock_value(oav.grid_snapshot.box_width, size_in_pixels)
    unpatched_snapshot_trigger = oav.grid_snapshot.trigger

    async def mock_grid_snapshot_trigger():
        await oav.grid_snapshot.last_path_full_overlay.set("test_1_y")
        await oav.grid_snapshot.last_path_outer.set("test_2_y")
        await oav.grid_snapshot.last_saved_path.set("test_3_y")
        return unpatched_snapshot_trigger()

    # Plain snapshots
    def next_snapshot():
        next_snapshot_idx = 1
        while True:
            yield f"/tmp/snapshot{next_snapshot_idx}.png"
            next_snapshot_idx += 1

    empty_response = MagicMock(spec=Response)
    empty_response.content = b""
    with (
        patch(
            "dodal.devices.areadetector.plugins.MJPG.requests.get",
            return_value=empty_response,
        ),
        patch("dodal.devices.areadetector.plugins.MJPG.Image.open"),
        patch.object(oav.grid_snapshot, "post_processing"),
        patch.object(
            oav.grid_snapshot, "trigger", side_effect=mock_grid_snapshot_trigger
        ),
        patch.object(oav.snapshot.last_saved_path, "get") as mock_last_saved_path,
    ):
        it_next_snapshot = next_snapshot()

        @AsyncStatus.wrap
        async def mock_rotation_snapshot_trigger():
            mock_last_saved_path.side_effect = lambda: next(it_next_snapshot)

        with patch.object(
            oav.snapshot,
            "trigger",
            side_effect=mock_rotation_snapshot_trigger,
        ):
            set_mock_value(oav.zoom_controller.level, "1.0")
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
