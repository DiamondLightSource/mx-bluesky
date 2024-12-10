from __future__ import annotations

import os
from collections.abc import Callable, Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from bluesky.run_engine import RunEngine
from dodal.devices.oav.oav_parameters import OAVParameters
from dodal.devices.oav.pin_image_recognition import PinTipDetection
from dodal.devices.synchrotron import SynchrotronMode
from ispyb.sqlalchemy import BLSample
from ophyd.sim import NullStatus
from ophyd_async.core import AsyncStatus
from ophyd_async.testing import set_mock_value

from mx_bluesky.hyperion.exceptions import WarningException
from mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan import (
    CrystalNotFoundException,
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
from mx_bluesky.hyperion.external_interaction.callbacks.sample_handling.sample_handling_callback import (
    SampleHandlingCallback,
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
    "xtalSnapshotFullPath1": "regex:/tmp/dls/i03/data/2024/cm31105-4/auto/123457/snapshots/\\d{6}_oav_snapshot_0\\.png",
    "xtalSnapshotFullPath2": "regex:/tmp/dls/i03/data/2024/cm31105-4/auto/123457/snapshots/\\d{"
    "6}_oav_snapshot_90\\.png",
    "xtalSnapshotFullPath3": "regex:/tmp/dls/i03/data/2024/cm31105-4/auto/123457/snapshots/\\d{"
    "6}_oav_snapshot_180\\.png",
    "xtalSnapshotFullPath4": "regex:/tmp/dls/i03/data/2024/cm31105-4/auto/123457/snapshots/\\d{"
    "6}_oav_snapshot_270\\.png",
}

ROTATION_DC_2_EXPECTED_VALUES = ROTATION_DC_EXPECTED_VALUES | {
    "xtalSnapshotFullPath1": "regex:/tmp/dls/i03/data/2024/cm31105-4/auto/123457/snapshots/\\d{6}_oav_snapshot_0\\.png",
    "xtalSnapshotFullPath2": "regex:/tmp/dls/i03/data/2024/cm31105-4/auto/123457/snapshots/\\d{"
    "6}_oav_snapshot_90\\.png",
    "xtalSnapshotFullPath3": "regex:/tmp/dls/i03/data/2024/cm31105-4/auto/123457/snapshots/\\d{"
    "6}_oav_snapshot_180\\.png",
    "xtalSnapshotFullPath4": "regex:/tmp/dls/i03/data/2024/cm31105-4/auto/123457/snapshots/\\d{"
    "6}_oav_snapshot_270\\.png",
}

SAMPLE_ID = 5461074


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


@pytest.fixture(autouse=True)
def use_dev_ispyb():
    with patch.dict(
        os.environ, values={"ISPYB_CONFIG_PATH": CONST.SIM.DEV_ISPYB_DATABASE_CFG}
    ):
        yield


@pytest.mark.s03
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
    ispyb_gridscan_cb = GridscanISPyBCallback()
    ispyb_rotation_cb = RotationISPyBCallback()
    robot_load_cb = RobotLoadISPyBCallback()
    # robot_load_cb.expeye = MagicMock()
    robot_load_cb.expeye.start_load = MagicMock(return_value=1234)
    robot_load_cb.expeye.end_load = MagicMock()
    robot_load_cb.expeye.update_barcode_and_snapshots = MagicMock()
    set_mock_value(
        load_centre_collect_composite.undulator_dcm.undulator.current_gap, 1.11
    )
    RE.subscribe(ispyb_gridscan_cb)
    RE.subscribe(ispyb_rotation_cb)
    RE.subscribe(robot_load_cb)
    RE(
        load_centre_collect_full(
            load_centre_collect_composite,
            load_centre_collect_params,
            oav_parameters_for_rotation,
        )
    )

    robot_load_cb.expeye.start_load.assert_called_once_with("cm37235", 4, 5461074, 2, 6)
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
        "Hyperion: Xray centring - Diffraction grid scan of 30 by 6 "
        "images in 20.0 um by 20.0 um steps. Top left (px): [130,130], "
        "bottom right (px): [874,278]. Aperture: ApertureValue.SMALL. ",
    )
    compare_comment(
        fetch_datacollection_attribute,
        ispyb_gridscan_cb.ispyb_ids.data_collection_ids[1],
        "Hyperion: Xray centring - Diffraction grid scan of 30 by 6 "
        "images in 20.0 um by 20.0 um steps. Top left (px): [130,130], "
        "bottom right (px): [874,278]. Aperture: ApertureValue.SMALL. ",
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
        "Sample position (µm): (-2309, -591, 341) Hyperion Rotation Scan -   Aperture: ApertureValue.SMALL. ",
    )
    assert fetch_blsample(SAMPLE_ID).blSampleStatus == "LOADED"  # type: ignore


@pytest.mark.s03
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

    assert fetch_blsample(SAMPLE_ID).blSampleStatus == "ERROR - beamline"


@pytest.mark.s03
def test_load_centre_collect_updates_bl_sample_status_pin_tip_detection_fail(
    load_centre_collect_composite: LoadCentreCollectComposite,
    load_centre_collect_params: LoadCentreCollect,
    oav_parameters_for_rotation: OAVParameters,
    pin_tip_no_pin_found: PinTipDetection,
    RE: RunEngine,
    fetch_blsample: Callable[..., Any],
):
    robot_load_cb = RobotLoadISPyBCallback()
    ispyb_gridscan_cb = GridscanISPyBCallback()
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

    assert fetch_blsample(SAMPLE_ID).blSampleStatus == "ERROR - sample"


@pytest.mark.s03
def test_load_centre_collect_updates_bl_sample_status_grid_detection_fail_tip_not_found(
    load_centre_collect_composite: LoadCentreCollectComposite,
    load_centre_collect_params: LoadCentreCollect,
    oav_parameters_for_rotation: OAVParameters,
    RE: RunEngine,
    fetch_blsample: Callable[..., Any],
):
    robot_load_cb = RobotLoadISPyBCallback()
    ispyb_gridscan_cb = GridscanISPyBCallback()
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

    assert fetch_blsample(SAMPLE_ID).blSampleStatus == "ERROR - sample"


@pytest.mark.s03
def test_load_centre_collect_updates_bl_sample_status_gridscan_no_diffraction(
    composite_with_no_diffraction: LoadCentreCollectComposite,
    load_centre_collect_params: LoadCentreCollect,
    oav_parameters_for_rotation: OAVParameters,
    RE: RunEngine,
    fetch_blsample: Callable[..., Any],
):
    robot_load_cb = RobotLoadISPyBCallback()
    ispyb_gridscan_cb = GridscanISPyBCallback()
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

    assert fetch_blsample(SAMPLE_ID).blSampleStatus == "ERROR - sample"


@pytest.mark.s03
def test_load_centre_collect_updates_bl_sample_status_rotation_failure(
    load_centre_collect_composite: LoadCentreCollectComposite,
    load_centre_collect_params: LoadCentreCollect,
    oav_parameters_for_rotation: OAVParameters,
    RE: RunEngine,
    fetch_blsample: Callable[..., Any],
):
    robot_load_cb = RobotLoadISPyBCallback()
    ispyb_gridscan_cb = GridscanISPyBCallback()
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

    assert fetch_blsample(SAMPLE_ID).blSampleStatus == "ERROR - beamline"
