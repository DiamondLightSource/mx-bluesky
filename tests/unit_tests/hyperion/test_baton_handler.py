import os
import sys
from typing import Any
from unittest.mock import ANY, MagicMock, call, patch

import pytest
from blueapi.core import BlueskyContext
from bluesky import plan_stubs as bps
from bluesky.run_engine import RunEngine
from dodal.devices.baton import Baton
from dodal.utils import get_beamline_based_on_environment_variable
from ophyd_async.testing import get_mock_put, set_mock_value
from pydantic import dataclasses

from mx_bluesky.common.utils.context import (
    device_composite_from_context,
    find_device_in_context,
)
from mx_bluesky.common.utils.exceptions import WarningException
from mx_bluesky.hyperion.baton_handler import (
    HYPERION_USER,
    NO_USER,
    initialise_udc,
    run_udc_when_requested,
)
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect
from mx_bluesky.hyperion.experiment_plans.load_centre_collect_full_plan import (
    LoadCentreCollectComposite,
)
from mx_bluesky.hyperion.utils.context import setup_context


@pytest.fixture()
def bluesky_context(i03_beamline_parameters):
    with (
        patch.dict(os.environ, {"BEAMLINE": "i03"}),
        patch("dodal.beamlines.i03.skip_baton", return_value=False),
    ):
        context = BlueskyContext()
        context.with_dodal_module(
            get_beamline_based_on_environment_variable(),
            mock=True,
            fake_with_ophyd_sim=True,
            connect_immediately=True,
        )

        yield context


@pytest.fixture()
async def baton(bluesky_context: BlueskyContext) -> Baton:
    baton = find_device_in_context(bluesky_context, "baton", Baton)
    set_mock_value(baton.requested_user, HYPERION_USER)
    return baton


@patch("mx_bluesky.hyperion.baton_handler.main_hyperion_loop", new=MagicMock())
@patch("mx_bluesky.hyperion.baton_handler.move_to_default_state", new=MagicMock())
@patch("mx_bluesky.hyperion.baton_handler.bps.sleep")
def test_loop_until_hyperion_requested(
    mock_sleep: MagicMock, bluesky_context: BlueskyContext, baton: Baton, RE: RunEngine
):
    set_mock_value(baton.requested_user, NO_USER)
    number_of_sleep_calls = 5

    def set_hyperion_requested(*args):
        yield from bps.null()
        set_mock_value(baton.requested_user, HYPERION_USER)

    mock_calls: list[Any] = [MagicMock()] * (number_of_sleep_calls - 1)
    mock_calls.append(set_hyperion_requested())
    mock_sleep.side_effect = mock_calls
    RE(run_udc_when_requested(bluesky_context, dev_mode=True))
    assert mock_sleep.call_count == number_of_sleep_calls


@patch("mx_bluesky.hyperion.baton_handler.main_hyperion_loop", new=MagicMock())
def test_when_hyperion_requested_then_hyperion_set_to_current_user(
    bluesky_context: BlueskyContext, baton: Baton, RE: RunEngine
):
    RE(run_udc_when_requested(bluesky_context, dev_mode=True))
    assert get_mock_put(baton.current_user).mock_calls[0] == call(
        HYPERION_USER, wait=True
    )


@patch("mx_bluesky.hyperion.baton_handler.main_hyperion_loop")
@patch("mx_bluesky.hyperion.baton_handler.move_to_default_state")
def test_when_hyperion_requested_then_default_state_and_collection_run(
    default_state: MagicMock,
    main_loop: MagicMock,
    bluesky_context: BlueskyContext,
    RE: RunEngine,
):
    parent_mock = MagicMock()
    parent_mock.attach_mock(default_state, "default_state")
    parent_mock.attach_mock(main_loop, "main_loop")

    RE(run_udc_when_requested(bluesky_context, dev_mode=True))
    assert parent_mock.method_calls == [call.default_state(), call.main_loop(ANY, ANY)]


async def _assert_baton_released(baton: Baton):
    assert await baton.requested_user.get_value() != HYPERION_USER
    assert get_mock_put(baton.current_user).mock_calls[-1] == call(NO_USER, wait=True)


@patch("mx_bluesky.hyperion.baton_handler.load_centre_collect_full")
@patch("mx_bluesky.hyperion.baton_handler.create_parameters_from_agamemnon")
async def test_when_exception_raised_in_collection_then_loop_stops_and_baton_released(
    agamemnon: MagicMock,
    collection: MagicMock,
    bluesky_context: BlueskyContext,
    baton: Baton,
    RE: RunEngine,
    load_centre_collect_params: LoadCentreCollect,
):
    collection.side_effect = ValueError()
    agamemnon.return_value = [load_centre_collect_params]
    with pytest.raises(ValueError):
        RE(run_udc_when_requested(bluesky_context, dev_mode=True))
    assert collection.call_count == 1
    await _assert_baton_released(baton)


@patch("mx_bluesky.hyperion.baton_handler.load_centre_collect_full")
@patch("mx_bluesky.hyperion.baton_handler.create_parameters_from_agamemnon")
async def test_when_warning_exception_raised_in_collection_then_loop_continues(
    agamemnon: MagicMock,
    collection: MagicMock,
    bluesky_context: BlueskyContext,
    baton: Baton,
    RE: RunEngine,
    load_centre_collect_params: LoadCentreCollect,
):
    collection.side_effect = [WarningException(), MagicMock(), ValueError()]
    agamemnon.return_value = [load_centre_collect_params]
    with pytest.raises(ValueError):
        RE(run_udc_when_requested(bluesky_context, dev_mode=True))
    assert collection.call_count == 3
    await _assert_baton_released(baton)


@patch("mx_bluesky.hyperion.baton_handler.move_to_default_state")
async def test_when_exception_raised_in_default_state_then_baton_released(
    default_state: MagicMock,
    bluesky_context: BlueskyContext,
    baton: Baton,
    RE: RunEngine,
):
    default_state.side_effect = [ValueError()]
    with pytest.raises(ValueError):
        RE(run_udc_when_requested(bluesky_context, dev_mode=True))
    await _assert_baton_released(baton)


@patch("mx_bluesky.hyperion.baton_handler.create_parameters_from_agamemnon")
async def test_when_exception_raised_in_getting_agamemnon_instruction_then_loop_stops_and_baton_released(
    agamemnon: MagicMock, bluesky_context: BlueskyContext, baton: Baton, RE: RunEngine
):
    agamemnon.side_effect = ValueError()
    with pytest.raises(ValueError):
        RE(run_udc_when_requested(bluesky_context, dev_mode=True))
    await _assert_baton_released(baton)


@patch("mx_bluesky.hyperion.baton_handler.create_parameters_from_agamemnon")
@patch("mx_bluesky.hyperion.baton_handler.load_centre_collect_full")
async def test_when_no_agamemnon_instructions_left_then_loop_stops_and_baton_released(
    collection: MagicMock,
    agamemnon: MagicMock,
    bluesky_context: BlueskyContext,
    baton: Baton,
    RE: RunEngine,
):
    agamemnon.return_value = None
    RE(run_udc_when_requested(bluesky_context, dev_mode=True))
    collection.assert_not_called()
    await _assert_baton_released(baton)


@patch("mx_bluesky.hyperion.baton_handler.create_parameters_from_agamemnon")
@patch("mx_bluesky.hyperion.baton_handler.load_centre_collect_full")
async def test_when_other_user_requested_collection_finished_then_baton_released(
    collection: MagicMock,
    agamemnon: MagicMock,
    bluesky_context: BlueskyContext,
    baton: Baton,
    RE: RunEngine,
    load_centre_collect_params: LoadCentreCollect,
):
    plan_continuing = MagicMock()
    agamemnon.return_value = [load_centre_collect_params]

    def fake_collection_with_baton_request_part_way_through(*args):
        yield from bps.null()
        yield from bps.mv(baton.requested_user, "OTHER_USER")
        plan_continuing()

    collection.side_effect = fake_collection_with_baton_request_part_way_through
    RE(run_udc_when_requested(bluesky_context, dev_mode=True))
    collection.assert_called_once()
    plan_continuing.assert_called_once()
    await _assert_baton_released(baton)
    assert await baton.requested_user.get_value() == "OTHER_USER"


@patch("mx_bluesky.hyperion.baton_handler.create_parameters_from_agamemnon")
@patch("mx_bluesky.hyperion.baton_handler.load_centre_collect_full")
@patch("mx_bluesky.hyperion.baton_handler.move_to_default_state")
async def test_when_multiple_agamemnon_instructions_then_default_state_only_run_once(
    default_state: MagicMock,
    collection: MagicMock,
    agamemnon: MagicMock,
    bluesky_context: BlueskyContext,
    RE: RunEngine,
):
    agamemnon.side_effect = [MagicMock(), MagicMock(), None]
    RE(run_udc_when_requested(bluesky_context, dev_mode=True))
    default_state.assert_called_once()


@patch.dict(os.environ, {"BEAMLINE": "i03"})
# @patch("mx_bluesky.hyperion.utils.context.get_beamline_based_on_environment_variable")
def test_initialise_udc_reloads_all_devices(
    RE: RunEngine,
    # mock_get_beamline: MagicMock
):
    # mock_get_beamline.side_effect = lambda: importlib.import_module("unit_tests.hyperion.fake_beamline")
    context = setup_context(True)
    devices_before_reset: LoadCentreCollectComposite = device_composite_from_context(
        context, LoadCentreCollectComposite
    )

    initialise_udc(context, True)

    devices_after_reset: LoadCentreCollectComposite = device_composite_from_context(
        context, LoadCentreCollectComposite
    )

    assert devices_before_reset.oav is not devices_after_reset.oav
    for f in dataclasses.fields():
        assert sys.getrefcount(f) == 2
