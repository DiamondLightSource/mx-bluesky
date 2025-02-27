from unittest.mock import ANY, MagicMock, call, patch

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
import pydantic
import pytest
from bluesky.simulators import assert_message_and_return_remaining
from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
from dodal.devices.dcm import DCM
from dodal.devices.undulator import Undulator
from dodal.devices.xbpm_feedback import XBPMFeedback

from mx_bluesky.common.parameters.constants import (
    PlanNameConstants,
)
from mx_bluesky.common.preprocessors.preprocessors import (
    transmission_and_xbpm_feedback_for_collection_for_fgs_decorator,
)
from tests.conftest import RunEngineSimulator


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class DeviceComposite:
    undulator: Undulator
    xbpm_feedback: XBPMFeedback
    attenuator: BinaryFilterAttenuator
    dcm: DCM


@pytest.fixture
def fake_composite(undulator, xbpm_feedback, attenuator, dcm) -> DeviceComposite:
    return DeviceComposite(undulator, xbpm_feedback, attenuator, dcm)


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
    fake_composite: DeviceComposite,
    sim_run_engine: RunEngineSimulator,
):
    @transmission_and_xbpm_feedback_for_collection_for_fgs_decorator(
        devices=fake_composite, desired_transmission_fraction=1
    )
    def my_boring_plan():
        yield from bps.null()

    msgs = sim_run_engine.simulate_plan(my_boring_plan())

    assert len(msgs) == 1
    assert msgs[0].command == "null"


def test_xbpm_preprocessor_runs_inserts_correct_plan_on_correct_message(
    fake_composite,
    sim_run_engine: RunEngineSimulator,
):
    @transmission_and_xbpm_feedback_for_collection_for_fgs_decorator(
        devices=fake_composite, desired_transmission_fraction=1
    )
    @bpp.set_run_key_decorator(PlanNameConstants.GRIDSCAN_OUTER)
    @bpp.run_decorator()
    def open_run_plan():
        yield from bps.null()

    msgs = sim_run_engine.simulate_plan(open_run_plan())
    assert_open_run_then_pause_xbpm_then_close_run_then_unpause(msgs)


@patch(
    "mx_bluesky.common.preprocessors.preprocessors._unpause_xbpm_feedback_and_set_transmission_to_1"
)
def test_xbpm_preprocessor_unpauses_xbpm_on_exception(
    mock_unpause_xbpm: MagicMock,
    fake_composite,
    sim_run_engine: RunEngineSimulator,
):
    @transmission_and_xbpm_feedback_for_collection_for_fgs_decorator(
        devices=fake_composite, desired_transmission_fraction=1
    )
    @bpp.set_run_key_decorator(PlanNameConstants.GRIDSCAN_OUTER)
    @bpp.run_decorator()
    def except_plan():
        yield from bps.null()
        print("no")
        raise Exception

    with pytest.raises(Exception):  # noqa: B017
        sim_run_engine.simulate_plan(except_plan())
    # We end up calling unpause twice in this case. One for close run and one for exception
    mock_unpause_xbpm.assert_has_calls([call(ANY, ANY)])
