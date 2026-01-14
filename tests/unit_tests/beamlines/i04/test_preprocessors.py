from unittest.mock import MagicMock

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
from bluesky.run_engine import RunEngine
from bluesky.simulators import assert_message_and_return_remaining
from ophyd_async.core import completed_status

from mx_bluesky.beamlines.i04.preprocessors.preprocessors import (
    i04_transmission_and_xbpm_feedback_for_collection_decorator,
)
from mx_bluesky.common.parameters.constants import (
    PlanNameConstants,
)
from tests.conftest import RunEngineSimulator, XBPMAndTransmissionWrapperComposite


def assert_open_run_sets_transmission_then_triggers_xbpm(msgs):
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "attenuator"
        and msg.args == (1.0,),
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "trigger" and msg.obj.name == "xbpm_feedback",
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "open_run"
        and msg.run == PlanNameConstants.GRIDSCAN_OUTER,
    )


def test_xbpm_preprocessor_does_nothing_on_non_specified_message(
    xbpm_and_transmission_wrapper_composite: XBPMAndTransmissionWrapperComposite,
    sim_run_engine: RunEngineSimulator,
):
    @i04_transmission_and_xbpm_feedback_for_collection_decorator(
        devices=xbpm_and_transmission_wrapper_composite,
        desired_transmission_fraction=1,
        run_key_to_wrap=PlanNameConstants.GRIDSCAN_OUTER,
    )
    @bpp.set_run_key_decorator(PlanNameConstants.DO_FGS)
    @bpp.run_decorator()
    def my_boring_plan():
        yield from bps.null()

    msgs = sim_run_engine.simulate_plan(my_boring_plan())

    assert len(msgs) == 3
    assert msgs[0].command == "open_run"
    assert msgs[1].command == "null"
    assert msgs[2].command == "close_run"


def test_xbpm_preprocessor_runs_inserts_correct_plan_on_correct_message(
    xbpm_and_transmission_wrapper_composite: XBPMAndTransmissionWrapperComposite,
    sim_run_engine: RunEngineSimulator,
):
    @i04_transmission_and_xbpm_feedback_for_collection_decorator(
        devices=xbpm_and_transmission_wrapper_composite,
        desired_transmission_fraction=1,
        run_key_to_wrap=PlanNameConstants.GRIDSCAN_OUTER,
    )
    @bpp.set_run_key_decorator(PlanNameConstants.GRIDSCAN_OUTER)
    @bpp.run_decorator()
    def open_run_plan():
        yield from bps.null()

    msgs = sim_run_engine.simulate_plan(open_run_plan())
    assert_open_run_sets_transmission_then_triggers_xbpm(msgs)


def test_xbpm_preprocessor_wraps_one_run_only_if_no_run_specified(
    xbpm_and_transmission_wrapper_composite: XBPMAndTransmissionWrapperComposite,
    run_engine: RunEngine,
):
    xbpm_and_transmission_wrapper_composite.attenuator.set = MagicMock(
        side_effect=lambda _: completed_status()
    )
    mock_set_transmission = xbpm_and_transmission_wrapper_composite.attenuator.set

    @i04_transmission_and_xbpm_feedback_for_collection_decorator(
        devices=xbpm_and_transmission_wrapper_composite, desired_transmission_fraction=1
    )
    @bpp.run_decorator()
    def first_plan():
        mock_set_transmission.assert_called_once()
        yield from second_plan()

    @bpp.set_run_key_decorator(PlanNameConstants.GRID_DETECT_AND_DO_GRIDSCAN)
    @bpp.run_decorator()
    def second_plan():
        yield from bps.null()

    run_engine(first_plan())
    mock_set_transmission.assert_called_once()
