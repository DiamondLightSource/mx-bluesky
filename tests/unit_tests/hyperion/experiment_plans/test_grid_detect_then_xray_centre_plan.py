import dataclasses
from collections.abc import Generator
from typing import cast
from unittest.mock import ANY, MagicMock, patch

import bluesky.plan_stubs as bps
import pytest
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from bluesky.utils import Msg
from dodal.devices.aperturescatterguard import ApertureValue
from dodal.devices.backlight import BacklightPosition
from dodal.devices.oav.oav_parameters import OAVParameters
from ophyd_async.testing import get_mock_put, set_mock_value

from mx_bluesky.common.parameters.gridscan import GridScanWithEdgeDetect
from mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan import (
    _fire_xray_centre_result_event,
)
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
    HyperionThreeDGridScan,
)

from ..conftest import OavGridSnapshotTestEvents
from .conftest import FLYSCAN_RESULT_LOW, FLYSCAN_RESULT_MED, sim_fire_event_on_open_run


def _fake_grid_detection(
    devices: OavGridDetectionComposite,
    parameters: OAVParameters,
    snapshot_template: str,
    snapshot_dir: str,
    grid_width_microns: float = 0,
    box_size_um: float = 0.0,
):
    oav = devices.oav
    set_mock_value(oav.grid_snapshot.box_width, 635)
    # first grid detection: x * y
    set_mock_value(oav.grid_snapshot.num_boxes_x, 10)
    set_mock_value(oav.grid_snapshot.num_boxes_y, 4)
    yield from bps.create(CONST.DESCRIPTORS.OAV_GRID_SNAPSHOT_TRIGGERED)
    yield from bps.read(oav)  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
    yield from bps.read(devices.smargon)
    yield from bps.save()

    # second grid detection: x * z, so num_boxes_y refers to smargon z
    set_mock_value(oav.grid_snapshot.num_boxes_x, 10)
    set_mock_value(oav.grid_snapshot.num_boxes_y, 1)
    yield from bps.create(CONST.DESCRIPTORS.OAV_GRID_SNAPSHOT_TRIGGERED)
    yield from bps.read(oav)  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
    yield from bps.read(devices.smargon)
    yield from bps.save()
    yield from _fire_xray_centre_result_event([FLYSCAN_RESULT_MED, FLYSCAN_RESULT_LOW])


def test_full_grid_scan(
    test_fgs_params: HyperionThreeDGridScan, test_config_files: dict[str, str]
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
    set_mock_value(grid_detect_devices.oav.zoom_controller.level, "7.5x")
    return grid_detect_devices


@patch(
    "mx_bluesky.hyperion.experiment_plans.grid_detect_then_xray_centre_plan.grid_detection_plan",
    autospec=True,
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.grid_detect_then_xray_centre_plan.flyscan_xray_centre_no_move",
    autospec=True,
)
async def test_detect_grid_and_do_gridscan(
    mock_flyscan: MagicMock,
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
            _do_detect_grid_and_gridscan_then_wait_for_backlight(
                composite, test_config_files, test_full_grid_scan_params
            ),
            test_full_grid_scan_params,
        )
    )
    # Verify we called the grid detection plan
    mock_grid_detection_plan.assert_called_once()

    # Check backlight was moved OUT
    get_mock_put(composite.backlight.position).assert_called_once_with(
        BacklightPosition.OUT, wait=ANY
    )

    # Check aperture was changed to SMALL
    assert (
        await composite.aperture_scatterguard.selected_aperture.get_value()
        == ApertureValue.SMALL
    )

    # Check we called out to underlying fast grid scan plan
    mock_flyscan.assert_called_once_with(ANY, ANY)


def _do_detect_grid_and_gridscan_then_wait_for_backlight(
    composite, test_config_files, test_full_grid_scan_params
):
    yield from detect_grid_and_do_gridscan(
        composite,
        parameters=test_full_grid_scan_params,
        oav_params=OAVParameters("xrayCentring", test_config_files["oav_config_json"]),
    )
    yield from bps.wait(CONST.WAIT.GRID_READY_FOR_DC)


@patch(
    "mx_bluesky.hyperion.experiment_plans.grid_detect_then_xray_centre_plan.grid_detection_plan",
    autospec=True,
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.grid_detect_then_xray_centre_plan.flyscan_xray_centre_no_move",
    autospec=True,
)
def test_when_full_grid_scan_run_then_parameters_sent_to_fgs_as_expected(
    mock_flyscan: MagicMock,
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

    params: HyperionThreeDGridScan = mock_flyscan.call_args[0][1]

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
    "mx_bluesky.hyperion.experiment_plans.grid_detect_then_xray_centre_plan.flyscan_xray_centre_no_move",
    autospec=True,
)
def test_detect_grid_and_do_gridscan_does_not_activate_ispyb_callback(
    mock_flyscan,
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
    "mx_bluesky.hyperion.experiment_plans.grid_detect_then_xray_centre_plan.change_aperture_then_move_to_xtal",
    autospec=True,
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.grid_detect_then_xray_centre_plan.grid_detection_plan",
    autospec=True,
    side_effect=_fake_grid_detection,
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.grid_detect_then_xray_centre_plan.flyscan_xray_centre_no_move",
    autospec=True,
)
def test_grid_detect_then_xray_centre_centres_on_the_first_flyscan_result(
    mock_flyscan: MagicMock,
    mock_grid_detection_plan: MagicMock,
    mock_change_aperture_then_move_to_xtal: MagicMock,
    grid_detect_devices_with_oav_config_params: GridDetectThenXRayCentreComposite,
    test_full_grid_scan_params: GridScanWithEdgeDetect,
    test_config_files: dict[str, str],
    RE: RunEngine,
):
    RE(
        grid_detect_then_xray_centre(
            grid_detect_devices_with_oav_config_params,
            test_full_grid_scan_params,
            test_config_files["oav_config_json"],
        )
    )
    mock_change_aperture_then_move_to_xtal.assert_called_once()
    assert (
        mock_change_aperture_then_move_to_xtal.mock_calls[0].args[0]
        == FLYSCAN_RESULT_MED
    )


@patch(
    "mx_bluesky.hyperion.experiment_plans.grid_detect_then_xray_centre_plan.grid_detection_plan",
    autospec=True,
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.grid_detect_then_xray_centre_plan.flyscan_xray_centre_no_move",
    autospec=True,
)
def test_grid_detect_then_xray_centre_activates_ispyb_callback(
    mock_flyscan,
    mock_grid_detection_plan,
    sim_run_engine: RunEngineSimulator,
    grid_detect_devices_with_oav_config_params: GridDetectThenXRayCentreComposite,
    test_full_grid_scan_params: GridScanWithEdgeDetect,
    test_config_files: dict[str, str],
):
    mock_grid_detection_plan.return_value = iter(
        [
            Msg("save_oav_grids"),
            Msg(
                "open_run",
                run=CONST.PLAN.FLYSCAN_RESULTS,
                xray_centre_results=[dataclasses.asdict(FLYSCAN_RESULT_MED)],
            ),
        ]
    )

    sim_run_engine.add_handler_for_callback_subscribes()
    sim_fire_event_on_open_run(sim_run_engine, CONST.PLAN.FLYSCAN_RESULTS)
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
