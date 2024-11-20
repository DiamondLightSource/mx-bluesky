from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from copy import deepcopy
from typing import Any, Literal

import pytest
from bluesky.run_engine import RunEngine
from dodal.devices.oav.oav_parameters import OAVParameters
from dodal.devices.synchrotron import SynchrotronMode

from mx_bluesky.common.parameters.components import IspybExperimentType
from mx_bluesky.common.parameters.gridscan import GridScanWithEdgeDetect
from mx_bluesky.hyperion.experiment_plans.grid_detect_then_xray_centre_plan import (
    GridDetectThenXRayCentreComposite,
    grid_detect_then_xray_centre,
)
from mx_bluesky.hyperion.experiment_plans.rotation_scan_plan import (
    RotationScanComposite,
    rotation_scan,
)
from mx_bluesky.hyperion.external_interaction.callbacks.common.ispyb_mapping import (
    populate_data_collection_group,
    populate_remaining_data_collection_info,
)
from mx_bluesky.hyperion.external_interaction.callbacks.rotation.ispyb_callback import (
    RotationISPyBCallback,
)
from mx_bluesky.hyperion.external_interaction.callbacks.xray_centre.ispyb_callback import (
    GridscanISPyBCallback,
)
from mx_bluesky.hyperion.external_interaction.callbacks.xray_centre.ispyb_mapping import (
    construct_comment_for_gridscan,
    populate_xy_data_collection_info,
    populate_xz_data_collection_info,
)
from mx_bluesky.hyperion.external_interaction.ispyb.data_model import (
    DataCollectionGridInfo,
    Orientation,
    ScanDataInfo,
)
from mx_bluesky.hyperion.external_interaction.ispyb.ispyb_store import (
    IspybIds,
    StoreInIspyb,
)
from mx_bluesky.hyperion.parameters.constants import CONST
from mx_bluesky.hyperion.parameters.gridscan import (
    HyperionThreeDGridScan,
)
from mx_bluesky.hyperion.parameters.rotation import RotationScan

from ...conftest import (
    DATA_COLLECTION_COLUMN_MAP,
    compare_actual_and_expected,
    compare_comment,
)
from .conftest import raw_params_from_file

EXPECTED_DATACOLLECTION_FOR_ROTATION = {
    "wavelength": 0.71,
    "beamSizeAtSampleX": 0.02,
    "beamSizeAtSampleY": 0.02,
    "exposureTime": 0.023,
    "undulatorGap1": 1.11,
    "synchrotronMode": SynchrotronMode.USER.value,
    "slitGapHorizontal": 0.123,
    "slitGapVertical": 0.234,
}

GRID_INFO_COLUMN_MAP = {
    s.lower(): s
    for s in [
        "gridInfoId",
        "dataCollectionGroupId",
        "xOffset",
        "yOffset",
        "dx_mm",
        "dy_mm",
        "steps_x",
        "steps_y",
        "meshAngle",
        "pixelsPerMicronX",
        "pixelsPerMicronY",
        "snapshot_offsetXPixel",
        "snapshot_offsetYPixel",
        "recordTimeStamp",
        "orientation",
        "workflowMeshId",
        "snaked",
        "dataCollectionId",
        "patchesX",
        "patchesY",
        "micronsPerPixelX",
        "micronsPerPixelY",
    ]
}


@pytest.fixture
def dummy_data_collection_group_info(dummy_params):
    return populate_data_collection_group(
        dummy_params,
    )


@pytest.fixture
def dummy_scan_data_info_for_begin(dummy_params):
    info = populate_xy_data_collection_info(
        dummy_params.detector_params,
    )
    info = populate_remaining_data_collection_info(None, None, info, dummy_params)
    return ScanDataInfo(
        data_collection_info=info,
    )


@pytest.fixture
def grid_detect_then_xray_centre_parameters():
    json_dict = raw_params_from_file(
        "tests/test_data/parameter_json_files/ispyb_gridscan_system_test_parameters.json"
    )
    return GridScanWithEdgeDetect(**json_dict)


def scan_xy_data_info_for_update(
    data_collection_group_id,
    dummy_params: HyperionThreeDGridScan,
    scan_data_info_for_begin,
):
    scan_data_info_for_update = deepcopy(scan_data_info_for_begin)
    scan_data_info_for_update.data_collection_info.parent_id = data_collection_group_id
    assert dummy_params is not None
    scan_data_info_for_update.data_collection_grid_info = DataCollectionGridInfo(
        dx_in_mm=dummy_params.x_step_size_um,
        dy_in_mm=dummy_params.y_step_size_um,
        steps_x=dummy_params.x_steps,
        steps_y=dummy_params.y_steps,
        microns_per_pixel_x=1.25,
        microns_per_pixel_y=1.25,
        # cast coordinates from numpy int64 to avoid mysql type conversion issues
        snapshot_offset_x_pixel=100,
        snapshot_offset_y_pixel=100,
        orientation=Orientation.HORIZONTAL,
        snaked=True,
    )
    scan_data_info_for_update.data_collection_info.comments = (
        construct_comment_for_gridscan(
            scan_data_info_for_update.data_collection_grid_info,
        )
    )
    return scan_data_info_for_update


def scan_data_infos_for_update_3d(
    ispyb_ids, scan_xy_data_info_for_update, dummy_params: HyperionThreeDGridScan
):
    xz_data_collection_info = populate_xz_data_collection_info(
        dummy_params.detector_params
    )

    assert dummy_params is not None
    data_collection_grid_info = DataCollectionGridInfo(
        dx_in_mm=dummy_params.x_step_size_um,
        dy_in_mm=dummy_params.z_step_size_um,
        steps_x=dummy_params.x_steps,
        steps_y=dummy_params.z_steps,
        microns_per_pixel_x=1.25,
        microns_per_pixel_y=1.25,
        # cast coordinates from numpy int64 to avoid mysql type conversion issues
        snapshot_offset_x_pixel=100,
        snapshot_offset_y_pixel=50,
        orientation=Orientation.HORIZONTAL,
        snaked=True,
    )
    xz_data_collection_info = populate_remaining_data_collection_info(
        construct_comment_for_gridscan(data_collection_grid_info),
        ispyb_ids.data_collection_group_id,
        xz_data_collection_info,
        dummy_params,
    )
    xz_data_collection_info.parent_id = ispyb_ids.data_collection_group_id

    scan_xz_data_info_for_update = ScanDataInfo(
        data_collection_info=xz_data_collection_info,
        data_collection_grid_info=(data_collection_grid_info),
    )
    return [scan_xy_data_info_for_update, scan_xz_data_info_for_update]


@pytest.fixture
def params_for_rotation_scan(test_rotation_params: RotationScan):
    test_rotation_params.rotation_increment_deg = 0.27
    test_rotation_params.exposure_time_s = 0.023
    test_rotation_params.detector_params.expected_energy_ev = 0.71
    return test_rotation_params


@pytest.mark.s03
def test_ispyb_get_comment_from_collection_correctly(fetch_comment: Callable[..., Any]):
    expected_comment_contents = (
        "Xray centring - "
        "Diffraction grid scan of 1 by 41 images, "
        "Top left [454,-4], Bottom right [455,772]"
    )

    assert fetch_comment(8292317) == expected_comment_contents

    assert fetch_comment(2) == ""


@pytest.mark.s03
def test_ispyb_deposition_comment_correct_on_failure(
    dummy_ispyb: StoreInIspyb,
    fetch_comment: Callable[..., Any],
    dummy_data_collection_group_info,
    dummy_scan_data_info_for_begin,
):
    ispyb_ids = dummy_ispyb.begin_deposition(
        dummy_data_collection_group_info, [dummy_scan_data_info_for_begin]
    )
    dummy_ispyb.end_deposition(ispyb_ids, "fail", "could not connect to devices")
    assert (
        fetch_comment(ispyb_ids.data_collection_ids[0])  # type: ignore
        == "DataCollection Unsuccessful reason: could not connect to devices"
    )


@pytest.mark.s03
def test_ispyb_deposition_comment_correct_for_3D_on_failure(
    dummy_ispyb_3d: StoreInIspyb,
    fetch_comment: Callable[..., Any],
    dummy_params,
    dummy_data_collection_group_info,
    dummy_scan_data_info_for_begin,
):
    ispyb_ids = dummy_ispyb_3d.begin_deposition(
        dummy_data_collection_group_info, [dummy_scan_data_info_for_begin]
    )
    scan_data_infos = generate_scan_data_infos(
        dummy_params,
        dummy_scan_data_info_for_begin,
        IspybExperimentType.GRIDSCAN_3D,
        ispyb_ids,
    )
    ispyb_ids = dummy_ispyb_3d.update_deposition(ispyb_ids, scan_data_infos)
    dcid1 = ispyb_ids.data_collection_ids[0]  # type: ignore
    dcid2 = ispyb_ids.data_collection_ids[1]  # type: ignore
    dummy_ispyb_3d.end_deposition(ispyb_ids, "fail", "could not connect to devices")
    assert (
        fetch_comment(dcid1)
        == "Hyperion: Xray centring - Diffraction grid scan of 40 by 20 images in 100.0 um by 100.0 um steps. Top left (px): [100,100], bottom right (px): [3300,1700]. DataCollection Unsuccessful reason: could not connect to devices"
    )
    assert (
        fetch_comment(dcid2)
        == "Hyperion: Xray centring - Diffraction grid scan of 40 by 10 images in 100.0 um by 100.0 um steps. Top left (px): [100,50], bottom right (px): [3300,850]. DataCollection Unsuccessful reason: could not connect to devices"
    )


@pytest.mark.s03
@pytest.mark.parametrize(
    "experiment_type, exp_num_of_grids, success",
    [
        (IspybExperimentType.GRIDSCAN_2D, 1, False),
        (IspybExperimentType.GRIDSCAN_2D, 1, True),
        (IspybExperimentType.GRIDSCAN_3D, 2, False),
        (IspybExperimentType.GRIDSCAN_3D, 2, True),
    ],
)
def test_can_store_2D_ispyb_data_correctly_when_in_error(
    experiment_type,
    exp_num_of_grids: Literal[1, 2],
    success: bool,
    fetch_comment: Callable[..., Any],
    dummy_params,
    dummy_data_collection_group_info,
    dummy_scan_data_info_for_begin,
):
    ispyb: StoreInIspyb = StoreInIspyb(CONST.SIM.DEV_ISPYB_DATABASE_CFG)
    ispyb_ids: IspybIds = ispyb.begin_deposition(
        dummy_data_collection_group_info, [dummy_scan_data_info_for_begin]
    )
    scan_data_infos = generate_scan_data_infos(
        dummy_params, dummy_scan_data_info_for_begin, experiment_type, ispyb_ids
    )

    ispyb_ids = ispyb.update_deposition(ispyb_ids, scan_data_infos)
    assert len(ispyb_ids.data_collection_ids) == exp_num_of_grids  # type: ignore
    assert len(ispyb_ids.grid_ids) == exp_num_of_grids  # type: ignore
    assert isinstance(ispyb_ids.data_collection_group_id, int)

    expected_comments = [
        (
            "Hyperion: Xray centring - Diffraction grid scan of 40 by 20 "
            "images in 100.0 um by 100.0 um steps. Top left (px): [100,100], bottom right (px): [3300,1700]."
        ),
        (
            "Hyperion: Xray centring - Diffraction grid scan of 40 by 10 "
            "images in 100.0 um by 100.0 um steps. Top left (px): [100,50], bottom right (px): [3300,850]."
        ),
    ]

    if success:
        ispyb.end_deposition(ispyb_ids, "success", "")
    else:
        ispyb.end_deposition(ispyb_ids, "fail", "In error")
        expected_comments = [
            e + " DataCollection Unsuccessful reason: In error"
            for e in expected_comments
        ]

    assert (
        not isinstance(ispyb_ids.data_collection_ids, int)
        and ispyb_ids.data_collection_ids is not None
    )
    for grid_no, dc_id in enumerate(ispyb_ids.data_collection_ids):
        assert fetch_comment(dc_id) == expected_comments[grid_no]


@pytest.mark.s03
@pytest.mark.skip(
    "Broken, fix in https://github.com/DiamondLightSource/mx-bluesky/issues/183"
)
def test_ispyb_deposition_in_gridscan(
    RE: RunEngine,
    grid_detect_then_xray_centre_composite: GridDetectThenXRayCentreComposite,
    grid_detect_then_xray_centre_parameters: GridScanWithEdgeDetect,
    fetch_datacollection_attribute: Callable[..., Any],
    fetch_datacollection_grid_attribute: Callable[..., Any],
    fetch_datacollection_position_attribute: Callable[..., Any],
):
    os.environ["ISPYB_CONFIG_PATH"] = CONST.SIM.DEV_ISPYB_DATABASE_CFG
    grid_detect_then_xray_centre_composite.s4_slit_gaps.xgap.user_readback.sim_put(0.1)  # type: ignore
    grid_detect_then_xray_centre_composite.s4_slit_gaps.ygap.user_readback.sim_put(0.1)  # type: ignore
    ispyb_callback = GridscanISPyBCallback()
    RE.subscribe(ispyb_callback)
    RE(
        grid_detect_then_xray_centre(
            grid_detect_then_xray_centre_composite,
            grid_detect_then_xray_centre_parameters,
        )
    )

    ispyb_ids = ispyb_callback.ispyb_ids
    DC_EXPECTED_VALUES = {
        "detectorid": 78,
        "axisstart": 0.0,
        "axisrange": 0,
        "axisend": 0,
        "focalspotsizeatsamplex": 0.02,
        "focalspotsizeatsampley": 0.02,
        "slitgapvertical": 0.1,
        "slitgaphorizontal": 0.1,
        "beamsizeatsamplex": 0.02,
        "beamsizeatsampley": 0.02,
        "transmission": 49.118,
        "datacollectionnumber": 1,
        "detectordistance": 100.0,
        "exposuretime": 0.12,
        "imagedirectory": "/tmp/",
        "imageprefix": "file_name",
        "imagesuffix": "h5",
        "numberofpasses": 1,
        "overlap": 0,
        "omegastart": 0,
        "startimagenumber": 1,
        "wavelength": 0.976254,
        "xbeam": 150.0,
        "ybeam": 160.0,
        "xtalsnapshotfullpath1": "test_1_y",
        "xtalsnapshotfullpath2": "test_2_y",
        "xtalsnapshotfullpath3": "test_3_y",
        "synchrotronmode": "User",
        "undulatorgap1": 1.11,
        "filetemplate": "file_name_1_master.h5",
        "numberofimages": 20 * 12,
    }
    compare_comment(
        fetch_datacollection_attribute,
        ispyb_ids.data_collection_ids[0],
        "Hyperion: Xray centring - Diffraction grid scan of 20 by 12 "
        "images in 20.0 um by 20.0 um steps. Top left (px): [100,161], "
        "bottom right (px): [239,244]. ApertureValue.SMALL. ",
    )
    compare_actual_and_expected(
        ispyb_ids.data_collection_ids[0],
        DC_EXPECTED_VALUES,
        fetch_datacollection_attribute,
        DATA_COLLECTION_COLUMN_MAP,
    )
    GRIDINFO_EXPECTED_VALUES = {
        "gridInfoId": ispyb_ids.grid_ids[0],
        "dx_mm": 0.02,
        "dy_mm": 0.02,
        "steps_x": 20,
        "steps_y": 12,
        "snapshot_offsetXPixel": 100,
        "snapshot_offsetYPixel": 161,
        "orientation": "horizontal",
        "snaked": True,
        "dataCollectionId": ispyb_ids.data_collection_ids[0],
        "micronsPerPixelX": 2.87,
        "micronsPerPixelY": 2.87,
    }

    compare_actual_and_expected(
        ispyb_ids.grid_ids[0],
        GRIDINFO_EXPECTED_VALUES,
        fetch_datacollection_grid_attribute,
        GRID_INFO_COLUMN_MAP,
    )
    position_id = fetch_datacollection_attribute(
        ispyb_ids.data_collection_ids[0], DATA_COLLECTION_COLUMN_MAP["positionid"]
    )
    assert position_id is None
    DC_EXPECTED_VALUES.update(
        {
            "axisstart": 90.0,
            "axisend": 90.0,
            "datacollectionnumber": 2,
            "omegastart": 90.0,
            "filetemplate": "file_name_2_master.h5",
            "numberofimages": 220,
        }
    )
    compare_actual_and_expected(
        ispyb_ids.data_collection_ids[1],
        DC_EXPECTED_VALUES,
        fetch_datacollection_attribute,
        DATA_COLLECTION_COLUMN_MAP,
    )
    compare_comment(
        fetch_datacollection_attribute,
        ispyb_ids.data_collection_ids[1],
        "Hyperion: Xray centring - Diffraction grid scan of 20 by 11 "
        "images in 20.0 um by 20.0 um steps. Top left (px): [100,165], "
        "bottom right (px): [239,241]. ApertureValue.SMALL. ",
    )
    position_id = fetch_datacollection_attribute(
        ispyb_ids.data_collection_ids[1], DATA_COLLECTION_COLUMN_MAP["positionid"]
    )
    assert position_id is None
    GRIDINFO_EXPECTED_VALUES.update(
        {
            "gridInfoId": ispyb_ids.grid_ids[1],
            "steps_y": 11.0,
            "snapshot_offsetYPixel": 165.0,
            "dataCollectionId": ispyb_ids.data_collection_ids[1],
        }
    )
    compare_actual_and_expected(
        ispyb_ids.grid_ids[1],
        GRIDINFO_EXPECTED_VALUES,
        fetch_datacollection_grid_attribute,
        GRID_INFO_COLUMN_MAP,
    )


@pytest.mark.s03
def test_ispyb_deposition_in_rotation_plan(
    composite_for_rotation_scan: RotationScanComposite,
    params_for_rotation_scan: RotationScan,
    oav_parameters_for_rotation: OAVParameters,
    RE: RunEngine,
    fetch_comment: Callable[..., Any],
    fetch_datacollection_attribute: Callable[..., Any],
    fetch_datacollection_position_attribute: Callable[..., Any],
):
    os.environ["ISPYB_CONFIG_PATH"] = CONST.SIM.DEV_ISPYB_DATABASE_CFG
    ispyb_cb = RotationISPyBCallback()
    RE.subscribe(ispyb_cb)

    RE(
        rotation_scan(
            composite_for_rotation_scan,
            params_for_rotation_scan,
            oav_parameters_for_rotation,
        )
    )

    dcid = ispyb_cb.ispyb_ids.data_collection_ids[0]
    assert dcid is not None
    assert (
        fetch_comment(dcid)
        == "Sample position (µm): (1, 2, 3) test  Aperture: ApertureValue.SMALL. "
    )

    expected_values = EXPECTED_DATACOLLECTION_FOR_ROTATION | {
        "xtalSnapshotFullPath1": "regex:/tmp/dls/i03/data/2024/cm31105-4/auto/123456/snapshots/\\d{6}_oav_snapshot_0"
        ".png",
        "xtalSnapshotFullPath2": "regex:/tmp/dls/i03/data/2024/cm31105-4/auto/123456/snapshots/\\d{6}_oav_snapshot_90"
        ".png",
        "xtalSnapshotFullPath3": "regex:/tmp/dls/i03/data/2024/cm31105-4/auto/123456/snapshots/\\d{6}_oav_snapshot_180"
        ".png",
        "xtalSnapshotFullPath4": "regex:/tmp/dls/i03/data/2024/cm31105-4/auto/123456/snapshots/\\d{6}_oav_snapshot_270"
        ".png",
    }

    compare_actual_and_expected(dcid, expected_values, fetch_datacollection_attribute)

    position_id = fetch_datacollection_attribute(
        dcid, DATA_COLLECTION_COLUMN_MAP["positionid"]
    )
    expected_values = {"posX": 0.001, "posY": 0.002, "posZ": 0.003}
    compare_actual_and_expected(
        position_id, expected_values, fetch_datacollection_position_attribute
    )


def generate_scan_data_infos(
    dummy_params,
    dummy_scan_data_info_for_begin: ScanDataInfo,
    experiment_type: IspybExperimentType,
    ispyb_ids: IspybIds,
) -> Sequence[ScanDataInfo]:
    xy_scan_data_info = scan_xy_data_info_for_update(
        ispyb_ids.data_collection_group_id, dummy_params, dummy_scan_data_info_for_begin
    )
    xy_scan_data_info.data_collection_id = ispyb_ids.data_collection_ids[0]
    if experiment_type == IspybExperimentType.GRIDSCAN_3D:
        scan_data_infos = scan_data_infos_for_update_3d(
            ispyb_ids, xy_scan_data_info, dummy_params
        )
    else:
        scan_data_infos = [xy_scan_data_info]
    return scan_data_infos
