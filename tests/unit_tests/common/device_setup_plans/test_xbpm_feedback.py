from unittest.mock import MagicMock

import bluesky.preprocessors as bpp
import pytest
from bluesky import plan_stubs as bps
from bluesky.run_engine import RunEngine
from bluesky.utils import FailedStatus
from dodal.devices.xbpm_feedback import Pause
from dodal.plans.preprocessors.verify_undulator_gap import (
    verify_undulator_gap_before_run_decorator,
)
from ophyd.status import Status
from ophyd_async.testing import set_mock_value
from tests.conftest import XBPMAndTransmissionWrapperComposite

from mx_bluesky.common.preprocessors.preprocessors import (
    transmission_and_xbpm_feedback_for_collection_decorator,
)


@pytest.fixture
def composite(
    xbpm_and_transmission_wrapper_composite: XBPMAndTransmissionWrapperComposite,
    done_status,
) -> XBPMAndTransmissionWrapperComposite:
    xbpm_and_transmission_wrapper_composite.undulator.set = MagicMock(
        return_value=done_status
    )

    return xbpm_and_transmission_wrapper_composite


async def test_xbpm_decorator_with_undulator_check_decorators(
    RE, composite: XBPMAndTransmissionWrapperComposite
):
    energy_in_kev = 11.3
    composite.dcm.energy_in_kev.user_readback.read = MagicMock(
        return_value={"value": {"value": energy_in_kev}}
    )

    @transmission_and_xbpm_feedback_for_collection_decorator(composite, 0.1)
    @verify_undulator_gap_before_run_decorator(composite)
    @bpp.run_decorator()
    def my_collection_plan():
        yield from bps.null()

    set_mock_value(composite.xbpm_feedback.pos_stable, 1)
    RE = RunEngine()
    RE(my_collection_plan())

    # Stop pyright from complaining
    assert isinstance(composite.xbpm_feedback.trigger, MagicMock)
    assert isinstance(composite.undulator.set, MagicMock)

    # Assert XBPM is stable
    composite.xbpm_feedback.trigger.assert_called_once()
    # Assert DCM energy is read after XBPM is stable
    composite.dcm.energy_in_kev.user_readback.read.assert_called_once()
    # Assert Undulator is finally set
    composite.undulator.set.assert_called_once()
    # Assert energy passed to the Undulator is the same as read from the DCM
    assert composite.undulator.set.call_args.args[0] == energy_in_kev


async def test_given_xpbm_checks_pass_when_plan_run_with_decorator_then_run_as_expected(
    RE, composite: XBPMAndTransmissionWrapperComposite
):
    expected_transmission = 0.3

    @transmission_and_xbpm_feedback_for_collection_decorator(
        composite, expected_transmission
    )
    @bpp.run_decorator()
    def my_collection_plan():
        read_transmission = yield from bps.rd(composite.attenuator.actual_transmission)
        assert read_transmission == expected_transmission
        pause_feedback = yield from bps.rd(composite.xbpm_feedback.pause_feedback)
        assert pause_feedback == Pause.PAUSE

    set_mock_value(composite.xbpm_feedback.pos_stable, 1)

    RE = RunEngine()
    RE(my_collection_plan())

    assert await composite.attenuator.actual_transmission.get_value() == 1.0
    assert await composite.xbpm_feedback.pause_feedback.get_value() == Pause.RUN


async def test_given_xbpm_checks_fail_when_plan_run_with_decorator_then_plan_not_run(
    RE, composite: XBPMAndTransmissionWrapperComposite
):
    mock = MagicMock()

    @transmission_and_xbpm_feedback_for_collection_decorator(composite, 0.1)
    @bpp.run_decorator()
    def my_collection_plan():
        mock()
        yield from bps.null()

    status = Status()
    status.set_exception(Exception())
    composite.xbpm_feedback.trigger = MagicMock(side_effect=lambda: status)

    RE = RunEngine()
    with pytest.raises(FailedStatus):
        RE(my_collection_plan())

    mock.assert_not_called()
    assert await composite.attenuator.actual_transmission.get_value() == 1.0
    assert await composite.xbpm_feedback.pause_feedback.get_value() == Pause.RUN


async def test_given_xpbm_checks_pass_and_plan_fails_when_plan_run_with_decorator_then_cleaned_up(
    RE, composite: XBPMAndTransmissionWrapperComposite
):
    set_mock_value(composite.xbpm_feedback.pos_stable, 1)

    class MyException(Exception):
        pass

    @transmission_and_xbpm_feedback_for_collection_decorator(composite, 0.1)
    @bpp.run_decorator()
    def my_collection_plan():
        yield from bps.null()
        raise MyException()

    RE = RunEngine()
    with pytest.raises(MyException):
        RE(my_collection_plan())

    assert await composite.attenuator.actual_transmission.get_value() == 1.0
    assert await composite.xbpm_feedback.pause_feedback.get_value() == Pause.RUN
