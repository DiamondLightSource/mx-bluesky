from unittest.mock import ANY, MagicMock, call, patch

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
import pytest
from bluesky.simulators import assert_message_and_return_remaining

from mx_bluesky.common.parameters.constants import (
    PlanNameConstants,
)
from mx_bluesky.common.preprocessors.preprocessors import (
    transmission_and_xbpm_feedback_for_collection_decorator,
)
from tests.conftest import RunEngineSimulator, XBPMAndTransmissionWrapperComposite


def assert_open_run_then_pause_xbpm_then_close_run_then_unpause(msgs):
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "trigger" and msg.obj.name == "xbpm_feedback",
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "open_run"
        and msg.run == PlanNameConstants.GRIDSCAN_OUTER,
    )

    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "close_run"
        and msg.run == PlanNameConstants.GRIDSCAN_OUTER,
    )

    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "attenuator"
        and msg.args == (1.0,),
    )


def test_xbpm_preprocessor_does_nothing_on_non_specified_message(
    xbpm_and_transmission_wrapper_composite: XBPMAndTransmissionWrapperComposite,
    sim_run_engine: RunEngineSimulator,
):
    @transmission_and_xbpm_feedback_for_collection_decorator(
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


def test_xbpm_preprocessor_does_nothing_with_no_run(
    xbpm_and_transmission_wrapper_composite: XBPMAndTransmissionWrapperComposite,
    sim_run_engine: RunEngineSimulator,
):
    @transmission_and_xbpm_feedback_for_collection_decorator(
        devices=xbpm_and_transmission_wrapper_composite,
        desired_transmission_fraction=1,
    )
    def my_boring_plan():
        yield from bps.null()

    msgs = sim_run_engine.simulate_plan(my_boring_plan())

    assert len(msgs) == 1
    assert msgs[0].command == "null"


def test_xbpm_preprocessor_runs_inserts_correct_plan_on_correct_message(
    xbpm_and_transmission_wrapper_composite: XBPMAndTransmissionWrapperComposite,
    sim_run_engine: RunEngineSimulator,
):
    @transmission_and_xbpm_feedback_for_collection_decorator(
        devices=xbpm_and_transmission_wrapper_composite,
        desired_transmission_fraction=1,
        run_key_to_wrap=PlanNameConstants.GRIDSCAN_OUTER,
    )
    @bpp.set_run_key_decorator(PlanNameConstants.GRIDSCAN_OUTER)
    @bpp.run_decorator()
    def open_run_plan():
        yield from bps.null()

    msgs = sim_run_engine.simulate_plan(open_run_plan())
    assert_open_run_then_pause_xbpm_then_close_run_then_unpause(msgs)


@patch(
    "mx_bluesky.common.preprocessors.preprocessors.unpause_xbpm_feedback_and_set_transmission_to_1"
)
def test_xbpm_preprocessor_unpauses_xbpm_on_exception(
    mock_unpause_xbpm: MagicMock,
    xbpm_and_transmission_wrapper_composite: XBPMAndTransmissionWrapperComposite,
    sim_run_engine: RunEngineSimulator,
):
    @transmission_and_xbpm_feedback_for_collection_decorator(
        devices=xbpm_and_transmission_wrapper_composite, desired_transmission_fraction=1
    )
    @bpp.set_run_key_decorator(PlanNameConstants.GRIDSCAN_OUTER)
    @bpp.run_decorator()
    def except_plan():
        yield from bps.null()
        raise Exception

    with pytest.raises(Exception):  # noqa: B017
        sim_run_engine.simulate_plan(except_plan())

    # Called once on exception and once on close_run
    mock_unpause_xbpm.assert_has_calls([call(ANY, ANY)])


@patch(
    "mx_bluesky.common.preprocessors.preprocessors.check_and_pause_feedback_and_verify_undulator_gap"
)
@patch(
    "mx_bluesky.common.preprocessors.preprocessors.unpause_xbpm_feedback_and_set_transmission_to_1"
)
def test_xbpm_preprocessor_wraps_one_run_only_if_no_run_specified(
    mock_pause: MagicMock,
    mock_unpause_xbpm: MagicMock,
    xbpm_and_transmission_wrapper_composite: XBPMAndTransmissionWrapperComposite,
    sim_run_engine: RunEngineSimulator,
):
    @transmission_and_xbpm_feedback_for_collection_decorator(
        devices=xbpm_and_transmission_wrapper_composite, desired_transmission_fraction=1
    )
    @bpp.set_run_key_decorator(PlanNameConstants.GRID_DETECT_AND_DO_GRIDSCAN)
    @bpp.run_decorator()
    def first_plan():
        yield from second_plan()

    @bpp.set_run_key_decorator(PlanNameConstants.GRID_DETECT_INNER)
    @bpp.run_decorator()
    def second_plan():
        yield from bps.null()

    sim_run_engine.simulate_plan(first_plan())
    mock_pause.assert_called_once()
    mock_unpause_xbpm.assert_called_once()
