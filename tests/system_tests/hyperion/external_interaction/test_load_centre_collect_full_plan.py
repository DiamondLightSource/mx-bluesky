from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest
from bluesky.run_engine import RunEngine
from dodal.devices.oav.oav_parameters import OAVParameters
from dodal.devices.synchrotron import SynchrotronMode
from ophyd_async.core import set_mock_value

from mx_bluesky.hyperion.experiment_plans.load_centre_collect_full_plan import (
    LoadCentreCollectComposite,
    load_centre_collect_full_plan,
)
from mx_bluesky.hyperion.external_interaction.callbacks.robot_load.ispyb_callback import (
    RobotLoadISPyBCallback,
)
from mx_bluesky.hyperion.external_interaction.callbacks.rotation.ispyb_callback import (
    RotationISPyBCallback,
)
from mx_bluesky.hyperion.external_interaction.callbacks.xray_centre.ispyb_callback import (
    GridscanISPyBCallback,
)
from mx_bluesky.hyperion.parameters.constants import CONST
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect

from ...conftest import (
    DATA_COLLECTION_COLUMN_MAP,
    compare_actual_and_expected,
    compare_comment,
)
from .conftest import raw_params_from_file


@pytest.fixture
def load_centre_collect_params():
    json_dict = raw_params_from_file(
        "tests/test_data/parameter_json_files/example_load_centre_collect_params.json"
    )
    return LoadCentreCollect(**json_dict)


@pytest.fixture
def load_centre_collect_composite(
    grid_detect_then_xray_centre_composite,
    composite_for_rotation_scan,
    thawer,
    vfm,
    mirror_voltages,
    undulator_dcm,
    webcam,
    lower_gonio,
):
    composite = LoadCentreCollectComposite(
        aperture_scatterguard=composite_for_rotation_scan.aperture_scatterguard,
        attenuator=composite_for_rotation_scan.attenuator,
        backlight=composite_for_rotation_scan.backlight,
        dcm=composite_for_rotation_scan.dcm,
        detector_motion=composite_for_rotation_scan.detector_motion,
        eiger=grid_detect_then_xray_centre_composite.eiger,
        flux=composite_for_rotation_scan.flux,
        robot=composite_for_rotation_scan.robot,
        smargon=composite_for_rotation_scan.smargon,
        undulator=composite_for_rotation_scan.undulator,
        synchrotron=composite_for_rotation_scan.synchrotron,
        s4_slit_gaps=composite_for_rotation_scan.s4_slit_gaps,
        sample_shutter=composite_for_rotation_scan.sample_shutter,
        zebra=grid_detect_then_xray_centre_composite.zebra,
        oav=grid_detect_then_xray_centre_composite.oav,
        xbpm_feedback=composite_for_rotation_scan.xbpm_feedback,
        zebra_fast_grid_scan=grid_detect_then_xray_centre_composite.zebra_fast_grid_scan,
        pin_tip_detection=grid_detect_then_xray_centre_composite.pin_tip_detection,
        zocalo=grid_detect_then_xray_centre_composite.zocalo,
        panda=grid_detect_then_xray_centre_composite.panda,
        panda_fast_grid_scan=grid_detect_then_xray_centre_composite.panda_fast_grid_scan,
        thawer=thawer,
        vfm=vfm,
        mirror_voltages=mirror_voltages,
        undulator_dcm=undulator_dcm,
        webcam=webcam,
        lower_gonio=lower_gonio,
    )

    set_mock_value(composite.dcm.bragg_in_degrees.user_readback, 5)

    yield composite


GRID_DC_1_EXPECTED_VALUES = {
    "BLSAMPLEID": 5461074,
    "detectorid": 78,
    "axisstart": 0.0,
    "axisrange": 0,
    "axisend": 0,
    "focalspotsizeatsamplex": 0.02,
    "focalspotsizeatsampley": 0.02,
    "slitgapvertical": 0.234,
    "slitgaphorizontal": 0.123,
    "beamsizeatsamplex": 0.02,
    "beamsizeatsampley": 0.02,
    "transmission": 100,
    "datacollectionnumber": 1,
    "detectordistance": 255.0,
    "exposuretime": 0.002,
    "imagedirectory": "/tmp/dls/i03/data/2024/cm31105-4/auto/123457/xraycentring/",
    "imageprefix": "robot_load_centring_file",
    "imagesuffix": "h5",
    "numberofpasses": 1,
    "overlap": 0,
    "omegastart": 0,
    "startimagenumber": 1,
    "wavelength": 0.71,
    "xbeam": 75.6027,
    "ybeam": 79.4935,
    "xtalsnapshotfullpath1": "test_1_y",
    "xtalsnapshotfullpath2": "test_2_y",
    "xtalsnapshotfullpath3": "test_3_y",
    "synchrotronmode": "User",
    "undulatorgap1": 1.11,
    "filetemplate": "robot_load_centring_file_1_master.h5",
    "numberofimages": 120,
}

GRID_DC_2_EXPECTED_VALUES = GRID_DC_1_EXPECTED_VALUES | {
    "axisstart": 90,
    "axisend": 90,
    "omegastart": 90,
    "datacollectionnumber": 2,
    "filetemplate": "robot_load_centring_file_2_master.h5",
    "numberofimages": 90,
}

ROTATION_DC_EXPECTED_VALUES = {
    "axisStart": 10,
    "axisEnd": 370,
    # "chiStart": 0, mx-bluesky 325
    "wavelength": 0.71,
    "beamSizeAtSampleX": 0.02,
    "beamSizeAtSampleY": 0.02,
    "exposureTime": 0.004,
    "undulatorGap1": 1.11,
    "synchrotronMode": SynchrotronMode.USER.value,
    "slitGapHorizontal": 0.123,
    "slitGapVertical": 0.234,
    "xtalSnapshotFullPath1": "/tmp/snapshot2.png",
    "xtalSnapshotFullPath2": "/tmp/snapshot3.png",
    "xtalSnapshotFullPath3": "/tmp/snapshot4.png",
    "xtalSnapshotFullPath4": "/tmp/snapshot5.png",
}

ROTATION_DC_2_EXPECTED_VALUES = ROTATION_DC_EXPECTED_VALUES | {
    "xtalSnapshotFullPath1": "/tmp/snapshot6.png",
    "xtalSnapshotFullPath2": "/tmp/snapshot7.png",
    "xtalSnapshotFullPath3": "/tmp/snapshot8.png",
    "xtalSnapshotFullPath4": "/tmp/snapshot9.png",
}


@pytest.mark.s03
def test_execute_load_centre_collect_full_plan(
    load_centre_collect_composite: LoadCentreCollectComposite,
    load_centre_collect_params: LoadCentreCollect,
    oav_parameters_for_rotation: OAVParameters,
    RE: RunEngine,
    fetch_datacollection_attribute: Callable[..., Any],
    fetch_datacollectiongroup_attribute: Callable[..., Any],
    fetch_datacollection_ids_for_group_id: Callable[..., Any],
):
    os.environ["ISPYB_CONFIG_PATH"] = CONST.SIM.DEV_ISPYB_DATABASE_CFG
    ispyb_gridscan_cb = GridscanISPyBCallback()
    ispyb_rotation_cb = RotationISPyBCallback()
    robot_load_cb = RobotLoadISPyBCallback()
    robot_load_cb.expeye = MagicMock()
    robot_load_cb.expeye.start_load.return_value = 1234
    RE.subscribe(ispyb_gridscan_cb)
    RE.subscribe(ispyb_rotation_cb)
    RE.subscribe(robot_load_cb)
    RE(
        load_centre_collect_full_plan(
            load_centre_collect_composite,
            load_centre_collect_params,
            oav_parameters_for_rotation,
        )
    )

    assert robot_load_cb.expeye.start_load.called_once_with("cm37235", 4, 5461074, 2, 6)
    assert robot_load_cb.expeye.update_barcode_and_snapshots(
        1234,
        "BARCODE",
        "/tmp/dls/i03/data/2024/cm31105-4/auto/123457/xraycentring/snapshots/160705_webcam_after_load.png",
        "/tmp/snapshot1.png",
    )
    assert robot_load_cb.expeye.end_load(1234, "success", "OK")

    # Compare gridscan collection
    compare_actual_and_expected(
        ispyb_gridscan_cb.ispyb_ids.data_collection_group_id,
        {"experimentType": "Mesh3D", "blSampleId": 5461074},
        fetch_datacollectiongroup_attribute,
    )
    compare_actual_and_expected(
        ispyb_gridscan_cb.ispyb_ids.data_collection_ids[0],
        GRID_DC_1_EXPECTED_VALUES,
        fetch_datacollection_attribute,
        DATA_COLLECTION_COLUMN_MAP,
    )
    compare_actual_and_expected(
        ispyb_gridscan_cb.ispyb_ids.data_collection_ids[1],
        GRID_DC_2_EXPECTED_VALUES,
        fetch_datacollection_attribute,
        DATA_COLLECTION_COLUMN_MAP,
    )

    compare_comment(
        fetch_datacollection_attribute,
        ispyb_gridscan_cb.ispyb_ids.data_collection_ids[0],
        "Hyperion: Xray centring - Diffraction grid scan of 30 by 4 "
        "images in 20.0 um by 20.0 um steps. Top left (px): [100,152], "
        "bottom right (px): [844,251]. Aperture: ApertureValue.SMALL. ",
    )
    compare_comment(
        fetch_datacollection_attribute,
        ispyb_gridscan_cb.ispyb_ids.data_collection_ids[1],
        "Hyperion: Xray centring - Diffraction grid scan of 30 by 3 "
        "images in 20.0 um by 20.0 um steps. Top left (px): [100,165], "
        "bottom right (px): [844,239]. Aperture: ApertureValue.SMALL. ",
    )

    rotation_dcg_id = ispyb_rotation_cb.ispyb_ids.data_collection_group_id
    rotation_dc_ids = fetch_datacollection_ids_for_group_id(rotation_dcg_id)
    compare_actual_and_expected(
        rotation_dcg_id,
        {"experimentType": "SAD", "blSampleId": 5461074},
        fetch_datacollectiongroup_attribute,
    )
    compare_actual_and_expected(
        rotation_dc_ids[0],
        ROTATION_DC_EXPECTED_VALUES,
        fetch_datacollection_attribute,
    )
    compare_actual_and_expected(
        rotation_dc_ids[1],
        ROTATION_DC_2_EXPECTED_VALUES,
        fetch_datacollection_attribute,
    )

    compare_comment(
        fetch_datacollection_attribute,
        ispyb_rotation_cb.ispyb_ids.data_collection_ids[0],
        "Sample position (µm): (675, 737, -381) Hyperion Rotation Scan -   Aperture: ApertureValue.SMALL. ",
    )
