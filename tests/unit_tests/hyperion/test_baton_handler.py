from unittest.mock import ANY, MagicMock, call, patch

import pytest
from bluesky import plan_stubs as bps
from bluesky.run_engine import RunEngine
from dodal.devices.baton import Baton
from ophyd_async.core import init_devices
from ophyd_async.testing import get_mock_put, set_mock_value

from mx_bluesky.common.utils.exceptions import WarningException
from mx_bluesky.hyperion.baton_handler import HYPERION_USER, NO_USER, baton_handler


@pytest.fixture()
async def baton() -> Baton:
    async with init_devices(mock=True):
        baton = Baton("")
    set_mock_value(baton.requested_user, HYPERION_USER)
    return baton


def test_loop_forever_if_not_hyperion_requested():
    pass


@patch("mx_bluesky.hyperion.baton_handler.main_hyperion_loop", new=MagicMock())
def test_when_hyperion_requested_then_hyperion_set_to_current_user(
    baton: Baton, RE: RunEngine
):
    RE(baton_handler(baton, MagicMock()))
    assert get_mock_put(baton.current_user).mock_calls[0] == call(
        HYPERION_USER, wait=True
    )


@patch("mx_bluesky.hyperion.baton_handler.main_hyperion_loop")
@patch("mx_bluesky.hyperion.baton_handler.move_to_default_state")
def test_when_hyperion_requested_then_default_state_and_collection_run(
    default_state: MagicMock, main_loop: MagicMock, baton: Baton, RE: RunEngine
):
    parent_mock = MagicMock()
    parent_mock.attach_mock(default_state, "default_state")
    parent_mock.attach_mock(main_loop, "main_loop")

    RE(baton_handler(baton, MagicMock()))
    assert parent_mock.method_calls == [call.default_state(), call.main_loop(ANY, ANY)]


def _assert_baton_released(baton: Baton):
    assert get_mock_put(baton.requested_user).mock_calls[-1] == call(NO_USER, wait=True)
    assert get_mock_put(baton.current_user).mock_calls[-1] == call(NO_USER, wait=True)


@patch("mx_bluesky.hyperion.baton_handler.load_centre_collect_full")
@patch("mx_bluesky.hyperion.baton_handler.create_parameters_from_agamemnon")
def test_when_exception_raised_in_collection_then_loop_stops_and_baton_released(
    agamemnon: MagicMock, collection: MagicMock, baton: Baton, RE: RunEngine
):
    collection.side_effect = ValueError()
    with pytest.raises(ValueError):
        RE(baton_handler(baton, MagicMock()))
    assert collection.call_count == 1
    _assert_baton_released(baton)


@patch("mx_bluesky.hyperion.baton_handler.load_centre_collect_full")
@patch("mx_bluesky.hyperion.baton_handler.create_parameters_from_agamemnon")
def test_when_warning_exception_raised_in_collection_then_loop_continues(
    agamemnon: MagicMock, collection: MagicMock, baton: Baton, RE: RunEngine
):
    collection.side_effect = [WarningException(), MagicMock(), ValueError()]
    with pytest.raises(ValueError):
        RE(baton_handler(baton, MagicMock()))
    assert collection.call_count == 3
    _assert_baton_released(baton)


@patch("mx_bluesky.hyperion.baton_handler.move_to_default_state")
def test_when_exception_raised_in_default_state_then_baton_released(
    default_state: MagicMock, baton: Baton, RE: RunEngine
):
    default_state.side_effect = [ValueError()]
    with pytest.raises(ValueError):
        RE(baton_handler(baton, MagicMock()))
    _assert_baton_released(baton)


@patch("mx_bluesky.hyperion.baton_handler.create_parameters_from_agamemnon")
def test_when_exception_raised_in_getting_agamemnon_instruction_then_loop_stops_and_baton_released(
    agamemnon: MagicMock, baton: Baton, RE: RunEngine
):
    agamemnon.side_effect = ValueError()
    with pytest.raises(ValueError):
        RE(baton_handler(baton, MagicMock()))
    _assert_baton_released(baton)


@patch("mx_bluesky.hyperion.baton_handler.create_parameters_from_agamemnon")
@patch("mx_bluesky.hyperion.baton_handler.load_centre_collect_full")
def test_when_no_agamemnon_instructions_left_then_loop_stops_and_baton_released(
    collection: MagicMock, agamemnon: MagicMock, baton: Baton, RE: RunEngine
):
    agamemnon.return_value = None
    RE(baton_handler(baton, MagicMock()))
    collection.assert_not_called()
    _assert_baton_released(baton)


@patch("mx_bluesky.hyperion.baton_handler.create_parameters_from_agamemnon")
@patch("mx_bluesky.hyperion.baton_handler.load_centre_collect_full")
def test_when_other_user_requested_collection_finished_then_baton_released(
    collection: MagicMock, agamemnon: MagicMock, baton: Baton, RE: RunEngine
):
    plan_continuing = MagicMock()

    def fake_collection_with_baton_request_part_way_through(*args):
        yield from bps.null()
        yield from bps.mv(baton.requested_user, "OTHER_USER")
        plan_continuing()

    collection.side_effect = fake_collection_with_baton_request_part_way_through
    RE(baton_handler(baton, MagicMock()))
    collection.assert_called_once()
    plan_continuing.assert_called_once()
    _assert_baton_released(baton)


@patch("mx_bluesky.hyperion.baton_handler.create_parameters_from_agamemnon")
@patch("mx_bluesky.hyperion.baton_handler.load_centre_collect_full")
@patch("mx_bluesky.hyperion.baton_handler.move_to_default_state")
def test_when_multiple_agamemnon_instructions_then_default_state_only_run_once(
    default_state: MagicMock,
    collection: MagicMock,
    agamemnon: MagicMock,
    baton: Baton,
    RE: RunEngine,
):
    agamemnon.side_effect = [MagicMock(), MagicMock(), None]
    RE(baton_handler(baton, MagicMock()))
    default_state.assert_called_once()
