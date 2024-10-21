from collections.abc import Generator
from typing import cast
from unittest.mock import ANY, MagicMock, patch

import bluesky.plan_stubs as bps
import pytest
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from bluesky.utils import Msg
from dodal.beamlines import i03
from dodal.devices.aperturescatterguard import ApertureValue
from dodal.devices.backlight import BacklightPosition
from dodal.devices.oav.oav_detector import OAVConfigParams
from dodal.devices.oav.oav_parameters import OAVParameters
from dodal.devices.smargon import Smargon

from mx_bluesky.hyperion.experiment_plans.grid_detect_then_xray_centre_plan import (
    GridDetectThenXRayCentreComposite,
    OavGridDetectionComposite,
    detect_grid_and_do_gridscan,
    grid_detect_then_xray_centre,
)
from mx_bluesky.hyperion.external_interaction.callbacks.xray_centre.ispyb_callback import (
    ispyb_activation_wrapper,
)
from mx_bluesky.hyperion.parameters.constants import CONST
from mx_bluesky.hyperion.parameters.gridscan import (
    GridScanWithEdgeDetect,
    ThreeDGridScan,
)

from ..conftest import OavGridSnapshotTestEvents


def _fake_grid_detection(
    devices: OavGridDetectionComposite,
    parameters: OAVParameters,
    snapshot_template: str,
    snapshot_dir: str,
    grid_width_microns: float = 0,
    box_size_um: float = 0.0,
):
    oav = i03.oav(fake_with_ophyd_sim=True)
    oav.grid_snapshot.box_width.put(635.00986)
    # first grid detection: x * y
    oav.grid_snapshot.num_boxes_x.put(10)
    oav.grid_snapshot.num_boxes_y.put(4)
    yield from bps.create(CONST.DESCRIPTORS.OAV_GRID_SNAPSHOT_TRIGGERED)
    yield from bps.read(oav.grid_snapshot)  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
    yield from bps.read(devices.smargon)
    yield from bps.save()

    # second grid detection: x * z, so num_boxes_y refers to smargon z
    oav.grid_snapshot.num_boxes_x.put(10)
    oav.grid_snapshot.num_boxes_y.put(1)
    yield from bps.create(CONST.DESCRIPTORS.OAV_GRID_SNAPSHOT_TRIGGERED)
    yield from bps.read(oav.grid_snapshot)  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
    yield from bps.read(devices.smargon)
    yield from bps.save()


@pytest.fixture
def grid_detect_devices(
    aperture_scatterguard: i03.ApertureScatterguard,
    backlight: i03.Backlight,
    detector_motion: i03.DetectorMotion,
    smargon: Smargon,
):
    return GridDetectThenXRayCentreComposite(
        aperture_scatterguard=aperture_scatterguard,
        attenuator=MagicMock(),
        backlight=backlight,
        detector_motion=detector_motion,
        eiger=MagicMock(),
        zebra_fast_grid_scan=MagicMock(),
        flux=MagicMock(),
        oav=MagicMock(),
        pin_tip_detection=MagicMock(),
        smargon=smargon,
        synchrotron=MagicMock(),
        s4_slit_gaps=MagicMock(),
        undulator=MagicMock(),
        xbpm_feedback=MagicMock(),
        zebra=MagicMock(),
        zocalo=MagicMock(),
        panda=MagicMock(),
        panda_fast_grid_scan=MagicMock(),
        dcm=MagicMock(),
        robot=MagicMock(),
        sample_shutter=MagicMock(),
    )


def test_full_grid_scan(
    test_fgs_params: ThreeDGridScan, test_config_files: dict[str, str]
):
    devices = MagicMock()
    plan = grid_detect_then_xray_centre(
        devices,
        cast(GridScanWithEdgeDetect, test_fgs_params),
        test_config_files["oav_config_json"],
    )
    assert isinstance(plan, Generator)


@pytest.fixture
def grid_detect_devices_with_oav_config_params(
    grid_detect_devices: GridDetectThenXRayCentreComposite,
    test_config_files: dict[str, str],
) -> GridDetectThenXRayCentreComposite:
    grid_detect_devices.oav.parameters = OAVConfigParams(
        test_config_files["zoom_params_file"], test_config_files["display_config"]
    )
    grid_detect_devices.oav.parameters.micronsPerXPixel = 0.806
    grid_detect_devices.oav.parameters.micronsPerYPixel = 0.806
    grid_detect_devices.oav.parameters.beam_centre_i = 549
    grid_detect_devices.oav.parameters.beam_centre_j = 347
    return grid_detect_devices


@patch(
    "mx_bluesky.hyperion.experiment_plans.grid_detect_then_xray_centre_plan.grid_detection_plan",
    autospec=True,
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.grid_detect_then_xray_centre_plan.flyscan_xray_centre",
    autospec=True,
)
async def test_detect_grid_and_do_gridscan(
    mock_flyscan_xray_centre_plan: MagicMock,
    mock_grid_detection_plan: MagicMock,
    grid_detect_devices_with_oav_config_params: GridDetectThenXRayCentreComposite,
    RE: RunEngine,
    test_full_grid_scan_params: GridScanWithEdgeDetect,
    test_config_files: dict,
):
    mock_grid_detection_plan.side_effect = _fake_grid_detection

    composite = grid_detect_devices_with_oav_config_params

    RE(
        ispyb_activation_wrapper(
            detect_grid_and_do_gridscan(
                composite,
                parameters=test_full_grid_scan_params,
                oav_params=OAVParameters(
                    "xrayCentring", test_config_files["oav_config_json"]
                ),
            ),
            test_full_grid_scan_params,
        )
    )
    # Verify we called the grid detection plan
    mock_grid_detection_plan.assert_called_once()

    # Check backlight was moved OUT
    assert await composite.backlight.position.get_value() == BacklightPosition.OUT

    # Check aperture was changed to SMALL
    assert (
        await composite.aperture_scatterguard.selected_aperture.get_value()
        == ApertureValue.SMALL
    )

    # Check we called out to underlying fast grid scan plan
    mock_flyscan_xray_centre_plan.assert_called_once_with(ANY, ANY)


@patch(
    "mx_bluesky.hyperion.experiment_plans.grid_detect_then_xray_centre_plan.grid_detection_plan",
    autospec=True,
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.grid_detect_then_xray_centre_plan.flyscan_xray_centre",
    autospec=True,
)
def test_when_full_grid_scan_run_then_parameters_sent_to_fgs_as_expected(
    mock_flyscan_xray_centre_plan: MagicMock,
    mock_grid_detection_plan: MagicMock,
    grid_detect_devices_with_oav_config_params: GridDetectThenXRayCentreComposite,
    RE: RunEngine,
    test_full_grid_scan_params: GridScanWithEdgeDetect,
    test_config_files: dict,
):
    oav_params = OAVParameters("xrayCentring", test_config_files["oav_config_json"])

    mock_grid_detection_plan.side_effect = _fake_grid_detection
    RE(
        ispyb_activation_wrapper(
            detect_grid_and_do_gridscan(
                grid_detect_devices_with_oav_config_params,
                parameters=test_full_grid_scan_params,
                oav_params=oav_params,
            ),
            test_full_grid_scan_params,
        )
    )

    params: ThreeDGridScan = mock_flyscan_xray_centre_plan.call_args[0][1]

    assert params.detector_params.num_triggers == 50

    assert params.FGS_params.x_axis.full_steps == 10
    assert params.FGS_params.y_axis.end == pytest.approx(1.511, 0.001)

    # Parameters can be serialized
    params.model_dump_json()


@patch(
    "mx_bluesky.hyperion.experiment_plans.grid_detect_then_xray_centre_plan.grid_detection_plan",
    autospec=True,
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.grid_detect_then_xray_centre_plan.flyscan_xray_centre",
    autospec=True,
)
def test_detect_grid_and_do_gridscan_does_not_activate_ispyb_callback(
    mock_flyscan_xray_centre,
    mock_grid_detection_plan,
    grid_detect_devices_with_oav_config_params: GridDetectThenXRayCentreComposite,
    sim_run_engine: RunEngineSimulator,
    test_full_grid_scan_params: GridScanWithEdgeDetect,
    test_config_files: dict[str, str],
):
    mock_grid_detection_plan.return_value = iter([Msg("save_oav_grids")])
    sim_run_engine.add_handler_for_callback_subscribes()
    sim_run_engine.add_callback_handler_for_multiple(
        "save_oav_grids",
        [
            [
                (
                    "descriptor",
                    OavGridSnapshotTestEvents.test_descriptor_document_oav_snapshot,  # type: ignore
                ),
                (
                    "event",
                    OavGridSnapshotTestEvents.test_event_document_oav_snapshot_xy,  # type: ignore
                ),
                (
                    "event",
                    OavGridSnapshotTestEvents.test_event_document_oav_snapshot_xz,  # type: ignore
                ),
            ]
        ],
    )

    msgs = sim_run_engine.simulate_plan(
        detect_grid_and_do_gridscan(
            grid_detect_devices_with_oav_config_params,
            test_full_grid_scan_params,
            OAVParameters("xrayCentring", test_config_files["oav_config_json"]),
        )
    )

    activations = [
        msg
        for msg in msgs
        if msg.command == "open_run"
        and "GridscanISPyBCallback" in msg.kwargs["activate_callbacks"]
    ]
    assert not activations


@patch(
    "mx_bluesky.hyperion.experiment_plans.grid_detect_then_xray_centre_plan.grid_detection_plan",
    autospec=True,
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.grid_detect_then_xray_centre_plan.flyscan_xray_centre",
    autospec=True,
)
def test_grid_detect_then_xray_centre_activates_ispyb_callback(
    mock_flyscan_xray_centre,
    mock_grid_detection_plan,
    sim_run_engine: RunEngineSimulator,
    grid_detect_devices_with_oav_config_params: GridDetectThenXRayCentreComposite,
    test_full_grid_scan_params: GridScanWithEdgeDetect,
    test_config_files: dict[str, str],
):
    mock_grid_detection_plan.return_value = iter([Msg("save_oav_grids")])

    sim_run_engine.add_handler_for_callback_subscribes()
    sim_run_engine.add_callback_handler_for_multiple(
        "save_oav_grids",
        [
            [
                (
                    "descriptor",
                    OavGridSnapshotTestEvents.test_descriptor_document_oav_snapshot,  # type: ignore
                ),
                (
                    "event",
                    OavGridSnapshotTestEvents.test_event_document_oav_snapshot_xy,  # type: ignore
                ),
                (
                    "event",
                    OavGridSnapshotTestEvents.test_event_document_oav_snapshot_xz,  # type: ignore
                ),
            ]
        ],
    )
    msgs = sim_run_engine.simulate_plan(
        grid_detect_then_xray_centre(
            grid_detect_devices_with_oav_config_params,
            test_full_grid_scan_params,
            test_config_files["oav_config_json"],
        )
    )

    assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "open_run"
        and "GridscanISPyBCallback" in msg.kwargs["activate_callbacks"],
    )
