import re
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from dodal.beamlines import i03
from dodal.devices.oav.oav_parameters import OAVConfigParams
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
    parameters = OAVConfigParams(
        test_config_files["zoom_params_file"], test_config_files["display_config"]
    )
    oav = i03.oav(fake_with_ophyd_sim=True, params=parameters)
    oav.zoom_controller.zrst.set("1.0x")
    oav.zoom_controller.onst.set("7.5x")
    oav.cam.array_size.array_size_x.sim_put(1024)
    oav.cam.array_size.array_size_y.sim_put(768)

    unpatched_method = oav.parameters.load_microns_per_pixel

    def patch_lmpp(zoom, xsize, ysize):
        unpatched_method(zoom, 1024, 768)

    # Grid snapshots
    oav.grid_snapshot.x_size.sim_put(1024)  # type: ignore
    oav.grid_snapshot.y_size.sim_put(768)  # type: ignore
    oav.grid_snapshot.top_left_x.set(50)
    oav.grid_snapshot.top_left_y.set(100)
    oav.grid_snapshot.box_width.set(0.1 * 1000 / 1.25)  # size in pixels
    unpatched_snapshot_trigger = oav.grid_snapshot.trigger

    def mock_grid_snapshot_trigger():
        oav.grid_snapshot.last_path_full_overlay.set("test_1_y")
        oav.grid_snapshot.last_path_outer.set("test_2_y")
        oav.grid_snapshot.last_saved_path.set("test_3_y")
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
        patch.object(
            oav.parameters,
            "load_microns_per_pixel",
            new=MagicMock(side_effect=patch_lmpp),
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
            oav.parameters.load_microns_per_pixel(1.0, 1024, 768)
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
