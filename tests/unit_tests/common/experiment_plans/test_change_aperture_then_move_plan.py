from unittest.mock import MagicMock, patch

import numpy
import pytest
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from dodal.devices.aperturescatterguard import ApertureScatterguard, ApertureValue
from dodal.devices.smargon import CombinedMove, Smargon, StubPosition

from mx_bluesky.common.experiment_plans.change_aperture_then_move_plan import (
    change_aperture,
    get_results_then_change_aperture_and_move_to_xtal,
    move_to_xtal,
)
from mx_bluesky.common.parameters.device_composites import (
    GridDetectThenXRayCentreComposite,
)
from mx_bluesky.common.parameters.gridscan import SpecifiedThreeDGridScan
from mx_bluesky.common.utils.xrc_result import XRayCentreEventHandler, XRayCentreResult


@pytest.fixture
def simple_flyscan_hit():
    return XRayCentreResult(
        centre_of_mass_mm=numpy.array([0.1, 0.2, 0.3]),
        bounding_box_mm=(
            numpy.array([0.09, 0.19, 0.29]),
            numpy.array([0.11, 0.21, 0.31]),
        ),
        max_count=20,
        total_count=57,
        sample_id=12345,
    )


@pytest.mark.parametrize("set_stub_offsets", [True, False])
def test_change_aperture_then_move_to_xtal_plans_happy_path(
    sim_run_engine: RunEngineSimulator,
    simple_flyscan_hit: XRayCentreResult,
    smargon: Smargon,
    aperture_scatterguard: ApertureScatterguard,
    set_stub_offsets: bool,
):
    msgs = sim_run_engine.simulate_plan(
        change_aperture(
            simple_flyscan_hit,
            aperture_scatterguard,
        )
    )
    msgs += sim_run_engine.simulate_plan(
        move_to_xtal(simple_flyscan_hit, smargon, set_stub_offsets)
    )

    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj is aperture_scatterguard.selected_aperture
        and msg.args[0] == ApertureValue.MEDIUM,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj is smargon
        and msg.args[0] == CombinedMove(x=0.1, y=0.2, z=0.3),
    )
    if set_stub_offsets:
        assert_message_and_return_remaining(
            msgs,
            lambda msg: msg.command == "set"
            and msg.obj is smargon.stub_offsets
            and msg.args[0] == StubPosition.CURRENT_AS_CENTER,
        )
    else:
        assert all(
            not (msg.command == "set" and msg.obj is smargon.stub_offsets)
            for msg in msgs
        )


@patch(
    "mx_bluesky.common.experiment_plans.change_aperture_then_move_plan.change_aperture"
)
@patch("mx_bluesky.common.experiment_plans.change_aperture_then_move_plan.move_to_xtal")
@patch(
    "mx_bluesky.common.experiment_plans.change_aperture_then_move_plan.fetch_xrc_results_from_zocalo"
)
def test_get_results_then_change_aperture_and_move_to_xtal_calls_expected_plans(
    mock_fetch_results_from_zocalo: MagicMock,
    mock_change_aperture: MagicMock,
    mock__get_xrc_results: MagicMock,
    run_engine: RunEngine,
    grid_detect_xrc_devices: GridDetectThenXRayCentreComposite,
    test_fgs_params: SpecifiedThreeDGridScan,
):
    mock_flyscan_event_handler = MagicMock(spec=XRayCentreEventHandler)
    mock_flyscan_event_handler.xray_centre_results = [0]

    run_engine(
        get_results_then_change_aperture_and_move_to_xtal(
            grid_detect_xrc_devices, test_fgs_params, mock_flyscan_event_handler
        )
    )
    mock__get_xrc_results.assert_called_once()
    mock_change_aperture.assert_called_once()
    mock_fetch_results_from_zocalo.assert_called_once()
