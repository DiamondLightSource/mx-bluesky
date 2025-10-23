from unittest.mock import MagicMock

import pytest
from bluesky import plan_stubs as bps
from bluesky.utils import FailedStatus
from dodal.beamlines import i03
from ophyd.status import Status
from ophyd_async.testing import get_mock_put

from mx_bluesky.common.device_setup_plans.utils import (
    start_preparing_data_collection_then_do_plan,
)


@pytest.fixture()
def mock_eiger():
    eiger = i03.eiger(mock=True)
    eiger.detector_params = MagicMock()
    eiger.async_stage = MagicMock()
    eiger.disarm_detector = MagicMock()
    return eiger


class MyTestError(Exception):
    pass


def test_given_plan_raises_when_exception_raised_then_eiger_disarmed_and_correct_exception_returned(
    beamstop_phase1, mock_eiger, detector_motion, run_engine
):
    def my_plan():
        yield from bps.null()
        raise MyTestError()

    eiger = mock_eiger

    with pytest.raises(MyTestError):
        run_engine(
            start_preparing_data_collection_then_do_plan(
                beamstop_phase1, eiger, detector_motion, 100, my_plan()
            )
        )

    # Check detector was armed
    eiger.async_stage.assert_called_once()

    eiger.disarm_detector.assert_called_once()


@pytest.fixture()
def null_plan():
    yield from bps.null()


def test_given_shutter_open_fails_then_eiger_disarmed_and_correct_exception_returned(
    beamstop_phase1, mock_eiger, null_plan, run_engine
):
    detector_motion = MagicMock()
    status = Status()
    status.set_exception(MyTestError())
    detector_motion.z.set = MagicMock(return_value=status)

    with pytest.raises(FailedStatus) as e:
        run_engine(
            start_preparing_data_collection_then_do_plan(
                beamstop_phase1, mock_eiger, detector_motion, 100, null_plan
            )
        )
    assert e.value.args[0] is status

    mock_eiger.async_stage.assert_called_once()
    detector_motion.z.set.assert_called_once()
    mock_eiger.disarm_detector.assert_called_once()


def test_given_detector_move_fails_then_eiger_disarmed_and_correct_exception_returned(
    beamstop_phase1, mock_eiger, detector_motion, null_plan, run_engine
):
    status = Status()
    status.set_exception(MyTestError())
    detector_motion.shutter.set = MagicMock(return_value=status)

    with pytest.raises(FailedStatus) as e:
        run_engine(
            start_preparing_data_collection_then_do_plan(
                beamstop_phase1, mock_eiger, detector_motion, 100, null_plan
            )
        )
    assert e.value.args[0] is status
    mock_eiger.async_stage.assert_called_once()

    def wait_for_set():
        yield from bps.wait(group="ready_for_data_collection")

    run_engine(wait_for_set())
    get_mock_put(detector_motion.z.user_setpoint).assert_called_once()
    mock_eiger.disarm_detector.assert_called_once()
