from __future__ import annotations

import os
from collections.abc import Callable, Generator
from contextlib import nullcontext
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import bluesky.plan_stubs as bps
import pytest
from bluesky.run_engine import RunEngine
from dodal.devices.oav.oav_parameters import OAVParameters
from dodal.devices.oav.pin_image_recognition import PinTipDetection
from dodal.devices.synchrotron import SynchrotronMode
from ispyb.sqlalchemy import BLSample
from ophyd.sim import NullStatus
from ophyd_async.core import AsyncStatus
from ophyd_async.testing import set_mock_value

from mx_bluesky.common.device_setup_plans.check_beamstop import BeamstopException
from mx_bluesky.common.external_interaction.callbacks.common.grid_detection_callback import (
    GridParamUpdate,
)
from mx_bluesky.common.external_interaction.callbacks.common.ispyb_mapping import (
    get_proposal_and_session_from_visit_string,
)
from mx_bluesky.common.external_interaction.callbacks.sample_handling.sample_handling_callback import (
    SampleHandlingCallback,
)
from mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback import (
    GridscanISPyBCallback,
)
from mx_bluesky.common.utils.exceptions import (
    CrystalNotFoundException,
    WarningException,
)
from mx_bluesky.hyperion.experiment_plans.grid_detect_then_xray_centre_plan import (
    detect_grid_and_do_gridscan,
)
from mx_bluesky.hyperion.experiment_plans.load_centre_collect_full_plan import (
    LoadCentreCollectComposite,
    load_centre_collect_full,
)
from mx_bluesky.hyperion.external_interaction.callbacks.robot_load.ispyb_callback import (
    RobotLoadISPyBCallback,
)
from mx_bluesky.hyperion.external_interaction.callbacks.rotation.ispyb_callback import (
    RotationISPyBCallback,
)
from mx_bluesky.hyperion.external_interaction.callbacks.snapshot_callback import (
    BeamDrawingCallback,
)
from mx_bluesky.hyperion.parameters.constants import CONST
from mx_bluesky.hyperion.parameters.gridscan import GridCommonWithHyperionDetectorParams
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect

from ....conftest import (
    TEST_RESULT_IN_BOUNDS_TOP_LEFT_BOX,
    TEST_RESULT_IN_BOUNDS_TOP_LEFT_GRID_CORNER,
    TEST_RESULT_MEDIUM,
    TEST_RESULT_OUT_OF_BOUNDS_BB,
    TEST_RESULT_OUT_OF_BOUNDS_COM,
    SimConstants,
    assert_images_pixelwise_equal,
    raw_params_from_file,
)
from ...conftest import (
    DATA_COLLECTION_COLUMN_MAP,
    compare_actual_and_expected,
    compare_comment,
)

SNAPSHOT_GENERATION_ZOCALO_RESULT = [
    {
        "centre_of_mass": [7.25, 12.2, 5.38],
        "max_voxel": [7, 12, 5],
        "max_count": 50000,
        "n_voxels": 35,
        "total_count": 100000,
        "bounding_box": [[1, 2, 3], [3, 4, 4]],
    }
]


@pytest.fixture
def load_centre_collect_params():
    json_dict = raw_params_from_file(
        "tests/test_data/parameter_json_files/example_load_centre_collect_params.json"
    )
    json_dict["visit"] = SimConstants.ST_VISIT
    json_dict["sample_id"] = SimConstants.ST_SAMPLE_ID
    return LoadCentreCollect(**json_dict)


@pytest.fixture
def load_centre_collect_composite(
    grid_detect_then_xray_centre_composite,
    beamstop_i03,
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
        beamstop=beamstop_i03,
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
    "BLSAMPLEID": SimConstants.ST_SAMPLE_ID,
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
    "wavelength": 0.976254,
    "xbeam": 75.6027,
    "ybeam": 79.4935,
    "xtalsnapshotfullpath1": "/tmp/dls/i03/data/2024/cm31105-4/auto/123457/xraycentring/snapshots/robot_load_centring_file_1_0_grid_overlay.png",
    "xtalsnapshotfullpath2": "/tmp/dls/i03/data/2024/cm31105-4/auto/123457/xraycentring/snapshots"
    "/robot_load_centring_file_1_0_outer_overlay.png",
    "xtalsnapshotfullpath3": "/tmp/dls/i03/data/2024/cm31105-4/auto/123457/xraycentring/snapshots/robot_load_centring_file_1_0.png",
    "synchrotronmode": "User",
    "undulatorgap1": 1.11,
    "filetemplate": "robot_load_centring_file_1_master.h5",
    "numberofimages": 180,
}

GRID_DC_2_EXPECTED_VALUES = GRID_DC_1_EXPECTED_VALUES | {
    "axisstart": 90,
    "axisend": 90,
    "omegastart": 90,
    "datacollectionnumber": 2,
    "filetemplate": "robot_load_centring_file_2_master.h5",
    "numberofimages": 180,
    "xtalsnapshotfullpath1": "/tmp/dls/i03/data/2024/cm31105-4/auto/123457/xraycentring/snapshots"
    "/robot_load_centring_file_1_90_grid_overlay.png",
    "xtalsnapshotfullpath2": "/tmp/dls/i03/data/2024/cm31105-4/auto/123457/xraycentring/snapshots"
    "/robot_load_centring_file_1_90_outer_overlay.png",
    "xtalsnapshotfullpath3": "/tmp/dls/i03/data/2024/cm31105-4/auto/123457/xraycentring/snapshots"
    "/robot_load_centring_file_1_90.png",
}

ROTATION_DC_EXPECTED_VALUES = {
    "axisStart": 10,
    "axisEnd": 370,
    # "chiStart": 0, mx-bluesky 325
    "wavelength": 0.976254,
    "beamSizeAtSampleX": 0.02,
    "beamSizeAtSampleY": 0.02,
    "exposureTime": 0.004,
    "undulatorGap1": 1.11,
    "synchrotronMode": SynchrotronMode.USER.value,
    "slitGapHorizontal": 0.123,
    "slitGapVertical": 0.234,
    "xtalSnapshotFullPath1": "regex:/tmp/dls/i03/data/2024/cm31105-4/auto/123457/snapshots/\\d{"
    "8}_oav_snapshot_0_with_beam_centre\\.png",
    "xtalSnapshotFullPath2": "regex:/tmp/dls/i03/data/2024/cm31105-4/auto/123457/snapshots/\\d{"
    "8}_oav_snapshot_90_with_beam_centre\\.png",
    "xtalSnapshotFullPath3": "regex:/tmp/dls/i03/data/2024/cm31105-4/auto/123457/snapshots/\\d{"
    "8}_oav_snapshot_180_with_beam_centre\\.png",
    "xtalSnapshotFullPath4": "regex:/tmp/dls/i03/data/2024/cm31105-4/auto/123457/snapshots/\\d{"
    "8}_oav_snapshot_270_with_beam_centre\\.png",
}

ROTATION_DC_2_EXPECTED_VALUES = ROTATION_DC_EXPECTED_VALUES | {
    "xtalSnapshotFullPath1": "regex:/tmp/dls/i03/data/2024/cm31105-4/auto/123457/snapshots/\\d{"
    "8}_oav_snapshot_0_with_beam_centre\\.png",
    "xtalSnapshotFullPath2": "regex:/tmp/dls/i03/data/2024/cm31105-4/auto/123457/snapshots/\\d{"
    "8}_oav_snapshot_90_with_beam_centre\\.png",
    "xtalSnapshotFullPath3": "regex:/tmp/dls/i03/data/2024/cm31105-4/auto/123457/snapshots/\\d{"
    "8}_oav_snapshot_180_with_beam_centre\\.png",
    "xtalSnapshotFullPath4": "regex:/tmp/dls/i03/data/2024/cm31105-4/auto/123457/snapshots/\\d{"
    "8}_oav_snapshot_270_with_beam_centre\\.png",
}


@pytest.fixture
def composite_with_no_diffraction(
    load_centre_collect_composite: LoadCentreCollectComposite,
) -> Generator[LoadCentreCollectComposite, Any, None]:
    zocalo = load_centre_collect_composite.zocalo

    @AsyncStatus.wrap
    async def mock_zocalo_complete():
        await zocalo._put_results([], {"dcid": 0, "dcgid": 0})

    with patch.object(zocalo, "trigger", side_effect=mock_zocalo_complete):
        yield load_centre_collect_composite


@pytest.mark.system_test
def test_execute_load_centre_collect_full(
    load_centre_collect_composite: LoadCentreCollectComposite,
    load_centre_collect_params: LoadCentreCollect,
    oav_parameters_for_rotation: OAVParameters,
    RE: RunEngine,
    fetch_datacollection_attribute: Callable[..., Any],
    fetch_datacollectiongroup_attribute: Callable[..., Any],
    fetch_datacollection_ids_for_group_id: Callable[..., Any],
    fetch_blsample: Callable[[int], BLSample],
):
    ispyb_gridscan_cb = GridscanISPyBCallback(
        param_type=GridCommonWithHyperionDetectorParams
    )
    ispyb_rotation_cb = RotationISPyBCallback()
    snapshot_cb = BeamDrawingCallback(emit=ispyb_rotation_cb)
    robot_load_cb = RobotLoadISPyBCallback()
    # robot_load_cb.expeye = MagicMock()
    robot_load_cb.expeye.start_load = MagicMock(return_value=1234)
    robot_load_cb.expeye.end_load = MagicMock()
    robot_load_cb.expeye.update_barcode_and_snapshots = MagicMock()
    set_mock_value(
        load_centre_collect_composite.undulator_dcm.undulator_ref().current_gap, 1.11
    )
    RE.subscribe(ispyb_gridscan_cb)
    RE.subscribe(snapshot_cb)
    RE.subscribe(robot_load_cb)
    RE(
        load_centre_collect_full(
            load_centre_collect_composite,
            load_centre_collect_params,
            oav_parameters_for_rotation,
        )
    )

    expected_proposal, expected_visit = get_proposal_and_session_from_visit_string(
        load_centre_collect_params.visit
    )
    expected_sample_id = load_centre_collect_params.sample_id
    robot_load_cb.expeye.start_load.assert_called_once_with(
        expected_proposal, expected_visit, expected_sample_id, 2, 6
    )
    # TODO re-enable this https://github.com/DiamondLightSource/mx-bluesky/issues/690
    # robot_load_cb.expeye.update_barcode_and_snapshots.assert_called_once_with(
    #     1234,
    #     "BARCODE",
    #     "/tmp/dls/i03/data/2024/cm31105-4/auto/123457/xraycentring/snapshots/160705_webcam_after_load.png",
    #     "/tmp/snapshot1.png",
    # )
    robot_load_cb.expeye.end_load.assert_called_once_with(1234, "success", "OK")

    # Compare gridscan collection
    compare_actual_and_expected(
        ispyb_gridscan_cb.ispyb_ids.data_collection_group_id,
        {"experimentType": "Mesh3D", "blSampleId": expected_sample_id},
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
        "MX-Bluesky: Xray centring 1 - Diffraction grid scan of 30 by 6 "
        "images in 20.0 um by 20.0 um steps. Top left (px): [130,130], "
        "bottom right (px): [874,278]. Aperture: Small. ",
    )
    compare_comment(
        fetch_datacollection_attribute,
        ispyb_gridscan_cb.ispyb_ids.data_collection_ids[1],
        "MX-Bluesky: Xray centring 2 - Diffraction grid scan of 30 by 6 "
        "images in 20.0 um by 20.0 um steps. Top left (px): [130,130], "
        "bottom right (px): [874,278]. Aperture: Small. ",
    )

    rotation_dcg_id = ispyb_rotation_cb.ispyb_ids.data_collection_group_id
    rotation_dc_ids = fetch_datacollection_ids_for_group_id(rotation_dcg_id)
    compare_actual_and_expected(
        rotation_dcg_id,
        {"experimentType": "SAD", "blSampleId": expected_sample_id},
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
        "Hyperion Rotation Scan -  Sample position (µm): (-2309, -591, 341) Aperture: "
        "Small. ",
    )
    assert fetch_blsample(expected_sample_id).blSampleStatus == "LOADED"  # type: ignore


@pytest.mark.system_test
def test_load_centre_collect_updates_bl_sample_status_robot_load_fail(
    load_centre_collect_composite: LoadCentreCollectComposite,
    load_centre_collect_params: LoadCentreCollect,
    oav_parameters_for_rotation: OAVParameters,
    RE: RunEngine,
    fetch_blsample: Callable[..., Any],
):
    robot_load_cb = RobotLoadISPyBCallback()
    sample_handling_cb = SampleHandlingCallback()
    RE.subscribe(robot_load_cb)
    RE.subscribe(sample_handling_cb)

    with (
        patch(
            "mx_bluesky.hyperion.experiment_plans.robot_load_and_change_energy.wait_for_smargon_not_disabled",
            side_effect=TimeoutError("Simulated timeout"),
        ),
        pytest.raises(TimeoutError, match="Simulated timeout"),
    ):
        RE(
            load_centre_collect_full(
                load_centre_collect_composite,
                load_centre_collect_params,
                oav_parameters_for_rotation,
            )
        )

    assert (
        fetch_blsample(load_centre_collect_params.sample_id).blSampleStatus
        == "ERROR - beamline"
    )


@pytest.mark.system_test
def test_load_centre_collect_updates_bl_sample_status_pin_tip_detection_fail(
    load_centre_collect_composite: LoadCentreCollectComposite,
    load_centre_collect_params: LoadCentreCollect,
    oav_parameters_for_rotation: OAVParameters,
    pin_tip_no_pin_found: PinTipDetection,
    RE: RunEngine,
    fetch_blsample: Callable[..., Any],
):
    robot_load_cb = RobotLoadISPyBCallback()
    ispyb_gridscan_cb = GridscanISPyBCallback(
        param_type=GridCommonWithHyperionDetectorParams
    )
    sample_handling_cb = SampleHandlingCallback()
    RE.subscribe(robot_load_cb)
    RE.subscribe(ispyb_gridscan_cb)
    RE.subscribe(sample_handling_cb)

    with pytest.raises(
        WarningException, match="Pin tip centring failed - pin too long/short.*"
    ):
        RE(
            load_centre_collect_full(
                load_centre_collect_composite,
                load_centre_collect_params,
                oav_parameters_for_rotation,
            )
        )

    assert (
        fetch_blsample(load_centre_collect_params.sample_id).blSampleStatus
        == "ERROR - sample"
    )


@pytest.mark.system_test
def test_load_centre_collect_updates_bl_sample_status_no_beamstop(
    load_centre_collect_composite: LoadCentreCollectComposite,
    load_centre_collect_params: LoadCentreCollect,
    oav_parameters_for_rotation: OAVParameters,
    RE: RunEngine,
    fetch_blsample: Callable[..., Any],
):
    sample_handling_cb = SampleHandlingCallback()
    RE.subscribe(sample_handling_cb)
    set_mock_value(load_centre_collect_composite.beamstop.x_mm.user_readback, 1)

    with pytest.raises(BeamstopException, match="Beamstop is not DATA_COLLECTION"):
        RE(
            load_centre_collect_full(
                load_centre_collect_composite,
                load_centre_collect_params,
                oav_parameters_for_rotation,
            )
        )

    assert (
        fetch_blsample(load_centre_collect_params.sample_id).blSampleStatus
        == "ERROR - beamline"
    )


@pytest.mark.system_test
def test_load_centre_collect_updates_bl_sample_status_grid_detection_fail_tip_not_found(
    load_centre_collect_composite: LoadCentreCollectComposite,
    load_centre_collect_params: LoadCentreCollect,
    oav_parameters_for_rotation: OAVParameters,
    RE: RunEngine,
    fetch_blsample: Callable[..., Any],
):
    robot_load_cb = RobotLoadISPyBCallback()
    ispyb_gridscan_cb = GridscanISPyBCallback(
        param_type=GridCommonWithHyperionDetectorParams
    )
    sample_handling_cb = SampleHandlingCallback()
    RE.subscribe(robot_load_cb)
    RE.subscribe(ispyb_gridscan_cb)
    RE.subscribe(sample_handling_cb)

    descriptor = None

    def wait_for_first_oav_grid(name: str, doc: dict):
        nonlocal descriptor
        if (
            name == "descriptor"
            and doc["name"] == CONST.DESCRIPTORS.OAV_GRID_SNAPSHOT_TRIGGERED
        ):
            descriptor = doc["uid"]
        if name == "event" and doc["descriptor"] == descriptor:
            # Trigger a fail to find the pin at 2nd grid detect
            set_mock_value(
                load_centre_collect_composite.pin_tip_detection.triggered_tip,
                PinTipDetection.INVALID_POSITION,
            )
            trigger = load_centre_collect_composite.pin_tip_detection.trigger
            trigger.return_value = NullStatus()  # type:ignore
            trigger.side_effect = None  # type: ignore

    RE.subscribe(wait_for_first_oav_grid)

    with pytest.raises(WarningException, match="No pin found after 5.0 seconds"):
        RE(
            load_centre_collect_full(
                load_centre_collect_composite,
                load_centre_collect_params,
                oav_parameters_for_rotation,
            )
        )

    assert (
        fetch_blsample(load_centre_collect_params.sample_id).blSampleStatus
        == "ERROR - sample"
    )


@pytest.mark.system_test
def test_load_centre_collect_updates_bl_sample_status_gridscan_no_diffraction(
    composite_with_no_diffraction: LoadCentreCollectComposite,
    load_centre_collect_params: LoadCentreCollect,
    oav_parameters_for_rotation: OAVParameters,
    RE: RunEngine,
    fetch_blsample: Callable[..., Any],
):
    robot_load_cb = RobotLoadISPyBCallback()
    ispyb_gridscan_cb = GridscanISPyBCallback(
        param_type=GridCommonWithHyperionDetectorParams
    )
    sample_handling_cb = SampleHandlingCallback()
    RE.subscribe(robot_load_cb)
    RE.subscribe(ispyb_gridscan_cb)
    RE.subscribe(sample_handling_cb)

    with pytest.raises(CrystalNotFoundException):
        RE(
            load_centre_collect_full(
                composite_with_no_diffraction,
                load_centre_collect_params,
                oav_parameters_for_rotation,
            )
        )

    assert (
        fetch_blsample(load_centre_collect_params.sample_id).blSampleStatus
        == "ERROR - sample"
    )


@pytest.mark.system_test
def test_load_centre_collect_updates_bl_sample_status_rotation_failure(
    load_centre_collect_composite: LoadCentreCollectComposite,
    load_centre_collect_params: LoadCentreCollect,
    oav_parameters_for_rotation: OAVParameters,
    RE: RunEngine,
    fetch_blsample: Callable[..., Any],
):
    robot_load_cb = RobotLoadISPyBCallback()
    ispyb_gridscan_cb = GridscanISPyBCallback(
        param_type=GridCommonWithHyperionDetectorParams
    )
    sample_handling_cb = SampleHandlingCallback()
    RE.subscribe(robot_load_cb)
    RE.subscribe(ispyb_gridscan_cb)
    RE.subscribe(sample_handling_cb)

    with (
        patch(
            "mx_bluesky.hyperion.experiment_plans.rotation_scan_plan.arm_zebra",
            side_effect=TimeoutError("Simulated timeout"),
        ),
        pytest.raises(TimeoutError, match="Simulated timeout"),
    ):
        RE(
            load_centre_collect_full(
                load_centre_collect_composite,
                load_centre_collect_params,
                oav_parameters_for_rotation,
            )
        )

    assert (
        fetch_blsample(load_centre_collect_params.sample_id).blSampleStatus
        == "ERROR - beamline"
    )


@pytest.mark.parametrize(
    "zocalo_result, expected_exception",
    [
        [TEST_RESULT_MEDIUM, nullcontext()],
        [TEST_RESULT_IN_BOUNDS_TOP_LEFT_BOX, nullcontext()],
        [TEST_RESULT_IN_BOUNDS_TOP_LEFT_GRID_CORNER, nullcontext()],
        [
            TEST_RESULT_OUT_OF_BOUNDS_COM,
            pytest.raises(IndexError, match=".* is outside the bounds of the grid"),
        ],
        [
            TEST_RESULT_OUT_OF_BOUNDS_BB,
            pytest.raises(IndexError, match=".* is outside the bounds of the grid"),
        ],
    ],
)
@pytest.mark.system_test
def test_load_centre_collect_gridscan_result_at_edge_of_grid(
    zocalo_result,
    expected_exception,
    load_centre_collect_composite: LoadCentreCollectComposite,
    load_centre_collect_params: LoadCentreCollect,
    oav_parameters_for_rotation: OAVParameters,
    RE: RunEngine,
):
    load_centre_collect_composite.zocalo.my_zocalo_result = zocalo_result
    ispyb_gridscan_cb = GridscanISPyBCallback(
        param_type=GridCommonWithHyperionDetectorParams
    )
    ispyb_rotation_cb = RotationISPyBCallback()
    robot_load_cb = RobotLoadISPyBCallback()
    robot_load_cb.expeye.start_load = MagicMock(return_value=1234)
    robot_load_cb.expeye.end_load = MagicMock()
    robot_load_cb.expeye.update_barcode_and_snapshots = MagicMock()
    set_mock_value(
        load_centre_collect_composite.undulator_dcm.undulator_ref().current_gap, 1.11
    )
    RE.subscribe(ispyb_gridscan_cb)
    RE.subscribe(ispyb_rotation_cb)
    RE.subscribe(robot_load_cb)
    with expected_exception:
        RE(
            load_centre_collect_full(
                load_centre_collect_composite,
                load_centre_collect_params,
                oav_parameters_for_rotation,
            )
        )


@pytest.mark.system_test
def test_execute_load_centre_collect_capture_rotation_snapshots(
    load_centre_collect_composite: LoadCentreCollectComposite,
    load_centre_collect_params: LoadCentreCollect,
    oav_parameters_for_rotation: OAVParameters,
    RE: RunEngine,
    fetch_datacollection_attribute: Callable[..., Any],
    fetch_datacollectiongroup_attribute: Callable[..., Any],
    fetch_datacollection_ids_for_group_id: Callable[..., Any],
    fetch_blsample: Callable[[int], BLSample],
    tmp_path: Path,
):
    load_centre_collect_params.multi_rotation_scan.snapshot_directory = tmp_path

    ispyb_gridscan_cb = GridscanISPyBCallback(
        param_type=GridCommonWithHyperionDetectorParams
    )
    ispyb_rotation_cb = RotationISPyBCallback()
    snapshot_callback = BeamDrawingCallback(emit=ispyb_rotation_cb)
    set_mock_value(
        load_centre_collect_composite.undulator_dcm.undulator_ref().current_gap, 1.11
    )
    RE.subscribe(ispyb_gridscan_cb)
    RE.subscribe(snapshot_callback)
    RE(
        load_centre_collect_full(
            load_centre_collect_composite,
            load_centre_collect_params,
            oav_parameters_for_rotation,
        )
    )

    EXPECTED_SNAPSHOT_VALUES = {
        "xtalSnapshotFullPath1": f"regex:{tmp_path}/\\d{{8}}_oav_snapshot_0_with_beam_centre\\.png",
        "xtalSnapshotFullPath2": f"regex:{tmp_path}/\\d{{8}}_oav_snapshot_90_with_beam_centre\\.png",
        "xtalSnapshotFullPath3": f"regex:{tmp_path}/\\d{{8}}_oav_snapshot_180_with_beam_centre\\.png",
        "xtalSnapshotFullPath4": f"regex:{tmp_path}/\\d{{8}}_oav_snapshot_270_with_beam_centre\\.png",
    }

    rotation_dcg_id = ispyb_rotation_cb.ispyb_ids.data_collection_group_id
    rotation_dc_ids = fetch_datacollection_ids_for_group_id(rotation_dcg_id)
    compare_actual_and_expected(
        rotation_dc_ids[0],
        EXPECTED_SNAPSHOT_VALUES,
        fetch_datacollection_attribute,
    )
    compare_actual_and_expected(
        rotation_dc_ids[1],
        EXPECTED_SNAPSHOT_VALUES,
        fetch_datacollection_attribute,
    )

    for column in [
        "xtalSnapshotFullPath1",
        "xtalSnapshotFullPath2",
        "xtalSnapshotFullPath3",
        "xtalSnapshotFullPath4",
    ]:
        filename = fetch_datacollection_attribute(rotation_dc_ids[0], column)
        assert_images_pixelwise_equal(
            filename, "tests/test_data/test_images/generate_snapshot_output.png"
        )


@pytest.fixture
def patch_detect_grid_and_do_gridscan_with_detected_pin_position(
    load_centre_collect_composite: LoadCentreCollectComposite,
):
    wrapped = detect_grid_and_do_gridscan

    # Before we do the grid scan, pretend we detected the pin at this position and move to it
    # This is the base snapshot position
    def wrapper(*args, **kwargs):
        yield from bps.mv(
            load_centre_collect_composite.smargon.x,
            -0.614,
            load_centre_collect_composite.smargon.y,
            0.0259,
            load_centre_collect_composite.smargon.z,
            0.250,
        )

        yield from wrapped(*args, **kwargs)

    with patch(
        "mx_bluesky.hyperion.experiment_plans.pin_centre_then_xray_centre_plan.detect_grid_and_do_gridscan",
    ) as patched_detect_grid:
        patched_detect_grid.side_effect = wrapper
        yield patched_detect_grid


@pytest.fixture
def grid_detect_for_snapshot_generation():
    fake_grid_params = GridParamUpdate(
        x_start_um=-598.4,
        y_start_um=-215.3,
        y2_start_um=-215.3,
        z_start_um=150.6,
        z2_start_um=150.6,
        x_steps=30,
        y_steps=20,
        z_steps=13,
        x_step_size_um=20,
        y_step_size_um=20,
        z_step_size_um=20,
    )
    with patch(
        "mx_bluesky.hyperion.experiment_plans.grid_detect_then_xray_centre_plan.GridDetectionCallback"
    ) as gdc:
        gdc.return_value.get_grid_parameters.return_value = fake_grid_params
        yield fake_grid_params


class TestGenerateSnapshot:
    @pytest.fixture()
    def test_config_files(self):
        return {
            "zoom_params_file": "tests/test_data/test_jCameraManZoomLevels.xml",
            "oav_config_json": "tests/test_data/test_daq_configuration/OAVCentring_hyperion.json",
            "display_config": "tests/test_data/test_daq_configuration/display.configuration",
        }

    @pytest.mark.system_test
    def test_load_centre_collect_generate_rotation_snapshots(
        self,
        load_centre_collect_composite: LoadCentreCollectComposite,
        load_centre_collect_params: LoadCentreCollect,
        grid_detect_for_snapshot_generation: GridParamUpdate,
        patch_detect_grid_and_do_gridscan_with_detected_pin_position: MagicMock,
        next_oav_system_test_image: MagicMock,
        RE: RunEngine,
        tmp_path: Path,
        test_config_files: dict,
        fetch_datacollection_attribute: Callable[..., Any],
        fetch_datacollection_ids_for_group_id: Callable[..., Any],
    ):
        oav_parameters = OAVParameters(
            oav_config_json=test_config_files["oav_config_json"],
            context="xrayCentring",
        )
        next_fake_snapshot = iter(
            [
                # 1 extra for robot load
                "tests/test_data/test_images/thau_1_91_0.png",
                "tests/test_data/test_images/thau_1_91_0.png",
                "tests/test_data/test_images/thau_1_91_90.png",
            ]
        )

        next_oav_system_test_image.side_effect = lambda: next(next_fake_snapshot)

        load_centre_collect_params.multi_rotation_scan.snapshot_directory = tmp_path
        load_centre_collect_params.robot_load_then_centre.snapshot_directory = (
            tmp_path / "grid_snapshots"
        )
        os.mkdir(load_centre_collect_params.robot_load_then_centre.snapshot_directory)
        load_centre_collect_params.multi_rotation_scan.use_grid_snapshots = True
        load_centre_collect_params.multi_rotation_scan.snapshot_omegas_deg = None
        load_centre_collect_composite.zocalo.my_zocalo_result = (
            SNAPSHOT_GENERATION_ZOCALO_RESULT
        )

        ispyb_gridscan_cb = GridscanISPyBCallback(
            param_type=GridCommonWithHyperionDetectorParams
        )
        ispyb_rotation_cb = RotationISPyBCallback()
        snapshot_callback = BeamDrawingCallback(emit=ispyb_rotation_cb)
        RE.subscribe(ispyb_gridscan_cb)
        RE.subscribe(snapshot_callback)
        RE(
            load_centre_collect_full(
                load_centre_collect_composite,
                load_centre_collect_params,
                oav_parameters,
            )
        )

        EXPECTED_GRID_SNAPSHOT_VALUES_0 = {
            "xtalSnapshotFullPath1": f"regex:{tmp_path}/grid_snapshots/robot_load_centring_file_1_0_grid_overlay.png",
            "xtalSnapshotFullPath2": f"regex:{tmp_path}/grid_snapshots/robot_load_centring_file_1_0_outer_overlay.png",
            "xtalSnapshotFullPath3": f"regex:{tmp_path}/grid_snapshots/robot_load_centring_file_1_0.png",
        }
        EXPECTED_GRID_SNAPSHOT_VALUES_1 = {
            "xtalSnapshotFullPath1": f"regex:{tmp_path}/grid_snapshots/robot_load_centring_file_1_90_grid_overlay.png",
            "xtalSnapshotFullPath2": f"regex:{tmp_path}/grid_snapshots/robot_load_centring_file_1_90_outer_overlay.png",
            "xtalSnapshotFullPath3": f"regex:{tmp_path}/grid_snapshots/robot_load_centring_file_1_90.png",
        }
        grid_dcg_id = ispyb_gridscan_cb.ispyb_ids.data_collection_group_id
        grid_dc_ids = fetch_datacollection_ids_for_group_id(grid_dcg_id)
        compare_actual_and_expected(
            grid_dc_ids[0],
            EXPECTED_GRID_SNAPSHOT_VALUES_0,
            fetch_datacollection_attribute,
        )
        compare_actual_and_expected(
            grid_dc_ids[1],
            EXPECTED_GRID_SNAPSHOT_VALUES_1,
            fetch_datacollection_attribute,
        )

        EXPECTED_ROTATION_SNAPSHOT_VALUES = {
            "xtalSnapshotFullPath1": f"regex:{tmp_path}/\\d{{8}}_oav_snapshot_robot_load_centring_file_1_0\\.png",
            "xtalSnapshotFullPath2": f"regex:{tmp_path}/\\d{{8}}_oav_snapshot_robot_load_centring_file_1_90\\.png",
        }

        rotation_dcg_id = ispyb_rotation_cb.ispyb_ids.data_collection_group_id
        rotation_dc_ids = fetch_datacollection_ids_for_group_id(rotation_dcg_id)
        compare_actual_and_expected(
            rotation_dc_ids[0],
            EXPECTED_ROTATION_SNAPSHOT_VALUES,
            fetch_datacollection_attribute,
        )
        compare_actual_and_expected(
            rotation_dc_ids[1],
            EXPECTED_ROTATION_SNAPSHOT_VALUES,
            fetch_datacollection_attribute,
        )

        for expected_path, actual_path in zip(
            [
                "tests/test_data/test_images/thau_1_91_expected_0.png",
                "tests/test_data/test_images/thau_1_91_expected_0.png",
                "tests/test_data/test_images/thau_1_91_expected_270.png",
                "tests/test_data/test_images/thau_1_91_expected_270.png",
            ],
            [
                fetch_datacollection_attribute(rotation_dc_ids[i], col)
                for col in ["xtalSnapshotFullPath1", "xtalSnapshotFullPath2"]
                for i in (0, 1)
            ],
            strict=False,
        ):
            assert_images_pixelwise_equal(actual_path, expected_path)
