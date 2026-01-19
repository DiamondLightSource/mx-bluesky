import asyncio
from unittest.mock import MagicMock

import bluesky.preprocessors as bpp
import pytest
from bluesky import RunEngine
from bluesky import plan_stubs as bps
from bluesky.utils import FailedStatus
from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
from dodal.devices.xbpm_feedback import Pause, XBPMFeedback
from dodal.plans.preprocessors.verify_undulator_gap import (
    verify_undulator_gap_before_run_decorator,
)
from ophyd_async.core import AsyncStatus, completed_status, set_mock_value

from mx_bluesky.common.device_setup_plans.xbpm_feedback import (
    unpause_xbpm_feedback_and_set_transmission_to_1,
)
from mx_bluesky.common.preprocessors.preprocessors import (
    pause_xbpm_feedback_during_collection_at_desired_transmission_decorator,
)
from tests.conftest import XBPMAndTransmissionWrapperComposite


@pytest.fixture
def composite(
    xbpm_and_transmission_wrapper_composite: XBPMAndTransmissionWrapperComposite,
) -> XBPMAndTransmissionWrapperComposite:
    xbpm_and_transmission_wrapper_composite.undulator.set = MagicMock(
        side_effect=lambda _: completed_status()
    )

    return xbpm_and_transmission_wrapper_composite


async def test_xbpm_decorator_with_undulator_check_decorators(
    run_engine, composite: XBPMAndTransmissionWrapperComposite
):
    energy_in_kev = 11.3
    composite.dcm.energy_in_keV.user_readback.read = MagicMock(
        return_value={"value": {"value": energy_in_kev}}
    )

    @pause_xbpm_feedback_during_collection_at_desired_transmission_decorator(
        composite, 0.1
    )
    @verify_undulator_gap_before_run_decorator(composite)
    @bpp.run_decorator()
    def my_collection_plan():
        yield from bps.null()

    set_mock_value(composite.xbpm_feedback.pos_stable, 1)
    run_engine(my_collection_plan())

    # Stop pyright from complaining
    assert isinstance(composite.xbpm_feedback.trigger, MagicMock)
    assert isinstance(composite.undulator.set, MagicMock)

    # Assert XBPM is stable
    composite.xbpm_feedback.trigger.assert_called_once()
    # Assert DCM energy is read after XBPM is stable
    composite.dcm.energy_in_keV.user_readback.read.assert_called_once()
    # Assert Undulator is finally set
    composite.undulator.set.assert_called_once()
    # Assert energy passed to the Undulator is the same as read from the DCM
    assert composite.undulator.set.call_args.args[0] == energy_in_kev


async def test_given_xpbm_checks_pass_when_plan_run_with_decorator_then_run_as_expected(
    run_engine, composite: XBPMAndTransmissionWrapperComposite
):
    expected_transmission = 0.3

    @pause_xbpm_feedback_during_collection_at_desired_transmission_decorator(
        composite, expected_transmission
    )
    @bpp.run_decorator()
    def my_collection_plan():
        read_transmission = yield from bps.rd(composite.attenuator.actual_transmission)
        assert read_transmission == expected_transmission
        pause_feedback = yield from bps.rd(composite.xbpm_feedback.pause_feedback)
        assert pause_feedback == Pause.PAUSE

    set_mock_value(composite.xbpm_feedback.pos_stable, 1)

    run_engine(my_collection_plan())

    assert await composite.attenuator.actual_transmission.get_value() == 1.0
    assert await composite.xbpm_feedback.pause_feedback.get_value() == Pause.RUN


async def test_given_xbpm_checks_fail_when_plan_run_with_decorator_then_plan_not_run(
    run_engine, composite: XBPMAndTransmissionWrapperComposite
):
    mock = MagicMock()

    @pause_xbpm_feedback_during_collection_at_desired_transmission_decorator(
        composite, 0.1
    )
    @bpp.run_decorator()
    def my_collection_plan():
        mock()
        yield from bps.null()

    composite.xbpm_feedback.trigger = MagicMock(
        side_effect=lambda: completed_status(Exception())
    )

    with pytest.raises(FailedStatus):
        run_engine(my_collection_plan())

    mock.assert_not_called()
    assert await composite.attenuator.actual_transmission.get_value() == 1.0
    assert await composite.xbpm_feedback.pause_feedback.get_value() == Pause.RUN


async def test_given_xpbm_checks_pass_and_plan_fails_when_plan_run_with_decorator_then_cleaned_up(
    run_engine, composite: XBPMAndTransmissionWrapperComposite
):
    set_mock_value(composite.xbpm_feedback.pos_stable, 1)

    class MyError(Exception):
        pass

    @pause_xbpm_feedback_during_collection_at_desired_transmission_decorator(
        composite, 0.1
    )
    @bpp.run_decorator()
    def my_collection_plan():
        yield from bps.null()
        raise MyError()

    with pytest.raises(MyError):
        run_engine(my_collection_plan())

    assert await composite.attenuator.actual_transmission.get_value() == 1.0
    assert await composite.xbpm_feedback.pause_feedback.get_value() == Pause.RUN


def test_unpause_feedback_and_set_transmission_to_1_times_out_if_timeout_specified(
    run_engine: RunEngine,
    xbpm_feedback: XBPMFeedback,
    attenuator: BinaryFilterAttenuator,
):
    @AsyncStatus.wrap
    async def wait_for_1_s():
        await asyncio.sleep(1)

    xbpm_feedback.trigger = MagicMock(side_effect=wait_for_1_s)
    with pytest.raises(TimeoutError):
        run_engine(
            unpause_xbpm_feedback_and_set_transmission_to_1(
                xbpm_feedback=xbpm_feedback,
                attenuator=attenuator,
                timeout_for_stable=0.1,
            )
        )
