from unittest.mock import MagicMock

import pytest
from bluesky import plan_stubs as bps
from bluesky.run_engine import RunEngine
from bluesky.utils import FailedStatus
from dodal.devices.xbpm_feedback import Pause
from ophyd.status import Status
from ophyd_async.testing import set_mock_value

from mx_bluesky.hyperion.device_setup_plans.xbpm_feedback import (
    transmission_and_xbpm_feedback_for_collection_decorator,
)


@pytest.fixture
def fake_undulator_set(undulator, done_status):
    undulator.set = MagicMock(return_value=done_status)
    return undulator


async def test_after_xbpm_is_stable_dcm_is_read_and_undulator_is_set_to_dcm_energy(
    RE,
    xbpm_feedback,
    fake_undulator_set,
    dcm,
    attenuator,
):
    energy_in_kev = 11.3
    dcm.energy_in_kev.user_readback.read = MagicMock(
        return_value={"value": {"value": energy_in_kev}}
    )

    @transmission_and_xbpm_feedback_for_collection_decorator(
        fake_undulator_set, xbpm_feedback, attenuator, dcm, 0.1
    )
    def my_collection_plan():
        yield from bps.null()

    set_mock_value(xbpm_feedback.pos_stable, 1)

    RE = RunEngine()
    RE(my_collection_plan())

    # Assert XBPM is stable
    xbpm_feedback.trigger.assert_called_once()
    # Assert DCM energy is read after XBPM is stable
    dcm.energy_in_kev.user_readback.read.assert_called_once()
    # Assert Undulator is finally set
    fake_undulator_set.set.assert_called_once()
    # Assert energy passed to the Undulator is the same as read from the DCM
    assert fake_undulator_set.set.call_args.args[0] == energy_in_kev


async def test_given_xpbm_checks_pass_when_plan_run_with_decorator_then_run_as_expected(
    RE,
    xbpm_feedback,
    fake_undulator_set,
    dcm,
    attenuator,
):
    expected_transmission = 0.3

    @transmission_and_xbpm_feedback_for_collection_decorator(
        fake_undulator_set, xbpm_feedback, attenuator, dcm, expected_transmission
    )
    def my_collection_plan():
        read_transmission = yield from bps.rd(attenuator.actual_transmission)
        assert read_transmission == expected_transmission
        pause_feedback = yield from bps.rd(xbpm_feedback.pause_feedback)
        assert pause_feedback == Pause.PAUSE

    set_mock_value(xbpm_feedback.pos_stable, 1)

    RE = RunEngine()
    RE(my_collection_plan())

    assert await attenuator.actual_transmission.get_value() == 1.0
    assert await xbpm_feedback.pause_feedback.get_value() == Pause.RUN


async def test_given_xbpm_checks_fail_when_plan_run_with_decorator_then_plan_not_run(
    RE,
    xbpm_feedback,
    fake_undulator_set,
    dcm,
    attenuator,
):
    mock = MagicMock()

    @transmission_and_xbpm_feedback_for_collection_decorator(
        fake_undulator_set, xbpm_feedback, attenuator, dcm, 0.1
    )
    def my_collection_plan():
        mock()
        yield from bps.null()

    status = Status()
    status.set_exception(Exception())
    xbpm_feedback.trigger = MagicMock(side_effect=lambda: status)

    RE = RunEngine()
    with pytest.raises(FailedStatus):
        RE(my_collection_plan())

    mock.assert_not_called()
    assert await attenuator.actual_transmission.get_value() == 1.0
    assert await xbpm_feedback.pause_feedback.get_value() == Pause.RUN


async def test_given_xpbm_checks_pass_and_plan_fails_when_plan_run_with_decorator_then_cleaned_up(
    RE,
    xbpm_feedback,
    fake_undulator_set,
    dcm,
    attenuator,
):
    set_mock_value(xbpm_feedback.pos_stable, 1)

    class MyException(Exception):
        pass

    @transmission_and_xbpm_feedback_for_collection_decorator(
        fake_undulator_set, xbpm_feedback, attenuator, dcm, 0.1
    )
    def my_collection_plan():
        yield from bps.null()
        raise MyException()

    RE = RunEngine()
    with pytest.raises(MyException):
        RE(my_collection_plan())

    assert await attenuator.actual_transmission.get_value() == 1.0
    assert await xbpm_feedback.pause_feedback.get_value() == Pause.RUN
