import numpy
import pytest
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from dodal.devices.aperturescatterguard import ApertureValue
from dodal.devices.smargon import StubPosition

from mx_bluesky.common.xrc_result import XRayCentreResult
from mx_bluesky.hyperion.experiment_plans.change_aperture_then_move_plan import (
    change_aperture_then_move_to_xtal,
)
from mx_bluesky.hyperion.experiment_plans.device_composites import (
    HyperionFlyScanXRayCentreComposite,
)
from mx_bluesky.hyperion.parameters.gridscan import HyperionSpecifiedThreeDGridScan


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
    fake_fgs_composite: HyperionFlyScanXRayCentreComposite,
    test_fgs_params: HyperionSpecifiedThreeDGridScan,
    set_stub_offsets: bool,
):
    test_fgs_params.features.set_stub_offsets = set_stub_offsets
    msgs = sim_run_engine.simulate_plan(
        change_aperture_then_move_to_xtal(
            simple_flyscan_hit, fake_fgs_composite, test_fgs_params
        )
    )

    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj is fake_fgs_composite.aperture_scatterguard
        and msg.args[0] == ApertureValue.MEDIUM,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj is fake_fgs_composite.smargon.x
        and msg.args[0] == 0.1,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj is fake_fgs_composite.smargon.y
        and msg.args[0] == 0.2,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj is fake_fgs_composite.smargon.z
        and msg.args[0] == 0.3,
    )
    if set_stub_offsets:
        assert_message_and_return_remaining(
            msgs,
            lambda msg: msg.command == "set"
            and msg.obj is fake_fgs_composite.smargon.stub_offsets
            and msg.args[0] == StubPosition.CURRENT_AS_CENTER,
        )
    else:
        assert all(
            not (
                msg.command == "set"
                and msg.obj is fake_fgs_composite.smargon.stub_offsets
            )
            for msg in msgs
        )
