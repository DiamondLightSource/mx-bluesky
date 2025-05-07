import numpy
import pytest
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from dodal.devices.aperturescatterguard import ApertureScatterguard, ApertureValue
from dodal.devices.smargon import Smargon, StubPosition

from mx_bluesky.common.experiment_plans.change_aperture_then_move_plan import (
    change_aperture_then_move_to_xtal,
)
from mx_bluesky.common.xrc_result import XRayCentreResult


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
    )


@pytest.mark.parametrize("set_stub_offsets", [True, False])
def test_change_aperture_then_move_to_xtal_happy_path(
    sim_run_engine: RunEngineSimulator,
    simple_flyscan_hit: XRayCentreResult,
    smargon: Smargon,
    aperture_scatterguard: ApertureScatterguard,
    set_stub_offsets: bool,
):
    msgs = sim_run_engine.simulate_plan(
        change_aperture_then_move_to_xtal(
            simple_flyscan_hit,
            smargon,
            aperture_scatterguard,
            set_stub_offsets,
        )
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
        and msg.obj is smargon.x
        and msg.args[0] == 0.1,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj is smargon.y
        and msg.args[0] == 0.2,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj is smargon.z
        and msg.args[0] == 0.3,
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
