import asyncio
import os
from asyncio import run_coroutine_threadsafe, sleep
from collections.abc import Generator
from concurrent.futures import Executor, Future, ThreadPoolExecutor
from dataclasses import fields
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest
from blueapi.core import BlueskyContext
from bluesky import Msg
from bluesky import plan_stubs as bps
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from dodal.devices.baton import Baton
from dodal.utils import get_beamline_based_on_environment_variable
from ophyd_async.testing import get_mock_put, set_mock_value

from mx_bluesky.common.parameters.components import (
    PARAMETER_VERSION,
    MxBlueskyParameters,
)
from mx_bluesky.common.parameters.constants import Status
from mx_bluesky.common.utils.context import (
    device_composite_from_context,
    find_device_in_context,
)
from mx_bluesky.common.utils.exceptions import WarningException
from mx_bluesky.hyperion.baton_handler import (
    HYPERION_USER,
    NO_USER,
    _initialise_udc,
    run_forever,
    run_udc_when_requested,
)
from mx_bluesky.hyperion.experiment_plans.load_centre_collect_full_plan import (
    LoadCentreCollectComposite,
)
from mx_bluesky.hyperion.parameters.components import Wait
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect
from mx_bluesky.hyperion.plan_runner import PlanException, PlanRunner
from mx_bluesky.hyperion.utils.context import setup_context


@pytest.fixture(scope="session")
def executor() -> Generator[Executor, Any, Any]:
    ex = ThreadPoolExecutor(max_workers=1, thread_name_prefix="test thread")
    yield ex
    ex.shutdown()


@pytest.fixture()
def base_bluesky_context():
    with patch.dict(os.environ, {"BEAMLINE": "i03"}):
        context = BlueskyContext()
        context.with_dodal_module(
            get_beamline_based_on_environment_variable(),
            mock=True,
            fake_with_ophyd_sim=True,
        )
        yield context


@pytest.fixture(autouse=True)
def patch_setup_devices():
    from mx_bluesky.hyperion.utils.context import setup_devices

    def patched_setup_devices(context: BlueskyContext, dev_mode: bool):
        setup_devices(context, True)
        if not isinstance(context.run_engine, MagicMock):
            # reapply requested user to the newly created fake baton
            # but not if it's a magicmock
            baton_with_requested_user(context, HYPERION_USER)

    # Patch setup_devices to patch the baton again when it is re-created
    with patch(
        "mx_bluesky.hyperion.baton_handler.setup_devices",
        side_effect=patched_setup_devices,
    ) as patched_func:
        yield patched_func


@pytest.fixture
def bluesky_context(i03_beamline_parameters, base_bluesky_context):
    # Baton for real run engine

    # Set the initial baton state
    baton_with_requested_user(base_bluesky_context, HYPERION_USER)

    yield base_bluesky_context


@pytest.fixture
def bluesky_context_with_sim_run_engine(
    sim_run_engine: RunEngineSimulator, base_bluesky_context: BlueskyContext
):
    baton_requested_user = HYPERION_USER

    # Baton for sim run engine
    def get_requested_user(msg):
        nonlocal baton_requested_user
        return {"readback": baton_requested_user}

    def set_requested_user(msg):
        nonlocal baton_requested_user
        baton_requested_user = msg.args[0]

    sim_run_engine.add_handler("locate", get_requested_user, "baton-requested_user")
    sim_run_engine.add_handler(
        "set",
        set_requested_user,  # type: ignore
        "baton-requested_user",
    )
    # sim_run_engine.add_handler("wait_for", lambda msg: [MagicMock(spec=asyncio.Future)])

    msgs = []

    def run_plan_in_sim(plan):
        msgs.extend(sim_run_engine.simulate_plan(plan))
        return sim_run_engine.return_value

    base_bluesky_context.run_engine = MagicMock(
        spec=RunEngine, side_effect=run_plan_in_sim
    )  # type: ignore

    # wait_for_connection in ensure_connected creates a bunch of awaitables
    # that will never be awaited by the simulator, let's not create them
    def dont_connect(*args, **kwargs):
        yield from bps.null()

    with patch("blueapi.utils.connect_devices.ensure_connected", dont_connect):
        yield msgs, base_bluesky_context


def baton_with_requested_user(
    bluesky_context: BlueskyContext, user: str = HYPERION_USER
) -> Baton:
    baton = find_device_in_context(bluesky_context, "baton", Baton)
    set_mock_value(baton.requested_user, user)
    return baton


@pytest.fixture()
def udc_runner(bluesky_context: BlueskyContext, RE: RunEngine) -> PlanRunner:
    bluesky_context.run_engine = RE
    return PlanRunner(bluesky_context)


@pytest.fixture
def mock_load_centre_collect():
    with (
        patch.dict(
            "mx_bluesky.hyperion.runner.PLAN_REGISTRY",
            load_centre_collect_full={"setup": MagicMock()},
        ),
        patch(
            "mx_bluesky.hyperion.baton_handler.load_centre_collect_full"
        ) as mock_plan,
    ):
        yield mock_plan


@pytest.fixture
def mock_create_params_from_agamemnon():
    with patch(
        "mx_bluesky.hyperion.baton_handler.create_parameters_from_agamemnon",
        return_value=[],
    ) as patched_func:
        yield patched_func


@patch("mx_bluesky.hyperion.baton_handler.bps.sleep")
@pytest.mark.timeout(10)
def test_loop_until_hyperion_requested(
    mock_sleep: MagicMock,
    udc_runner: PlanRunner,
    bluesky_context: BlueskyContext,
    mock_create_params_from_agamemnon: MagicMock,
):
    baton = baton_with_requested_user(bluesky_context, NO_USER)
    number_of_sleep_calls = 5

    def set_hyperion_requested(*args):
        yield from bps.null()
        set_mock_value(baton.requested_user, HYPERION_USER)

    mock_calls: list[Any] = [MagicMock()] * (number_of_sleep_calls - 1)
    mock_calls.append(set_hyperion_requested())
    mock_sleep.side_effect = mock_calls

    run_udc_when_requested(bluesky_context, udc_runner)

    assert mock_sleep.call_count == number_of_sleep_calls


def test_when_hyperion_requested_then_hyperion_set_to_current_user(
    bluesky_context: BlueskyContext,
    udc_runner: PlanRunner,
    mock_create_params_from_agamemnon: MagicMock,
):
    baton = find_device_in_context(bluesky_context, "baton", Baton)

    run_udc_when_requested(bluesky_context, udc_runner)

    assert get_mock_put(baton.current_user).mock_calls[0] == call(
        HYPERION_USER, wait=True
    )


@patch("mx_bluesky.hyperion.baton_handler._move_to_default_state")
def test_when_hyperion_requested_then_default_state_and_collection_run(
    default_state: MagicMock,
    bluesky_context: BlueskyContext,
    udc_runner: PlanRunner,
    mock_create_params_from_agamemnon: MagicMock,
):
    parent_mock = MagicMock()
    parent_mock.attach_mock(default_state, "default_state")
    parent_mock.attach_mock(mock_create_params_from_agamemnon, "main_loop")

    run_udc_when_requested(bluesky_context, udc_runner)
    assert parent_mock.method_calls == [call.default_state(), call.main_loop()]


async def _assert_baton_released(baton: Baton):
    assert await baton.requested_user.get_value() != HYPERION_USER
    assert get_mock_put(baton.current_user).mock_calls[-1] == call(NO_USER, wait=True)


@patch("mx_bluesky.hyperion.baton_handler.create_parameters_from_agamemnon")
async def test_when_exception_raised_in_collection_then_loop_stops_and_baton_released(
    agamemnon: MagicMock,
    mock_load_centre_collect: MagicMock,
    bluesky_context: BlueskyContext,
    load_centre_collect_params: LoadCentreCollect,
    udc_runner: PlanRunner,
):
    mock_load_centre_collect.side_effect = ValueError()
    agamemnon.return_value = [load_centre_collect_params]

    with pytest.raises(PlanException) as e:
        run_udc_when_requested(bluesky_context, udc_runner)

    assert isinstance(e.value.__cause__, ValueError)
    baton = find_device_in_context(bluesky_context, "baton", Baton)
    assert mock_load_centre_collect.call_count == 1
    await _assert_baton_released(baton)


@patch("mx_bluesky.hyperion.baton_handler.create_parameters_from_agamemnon")
async def test_when_warning_exception_raised_in_collection_then_loop_continues(
    agamemnon: MagicMock,
    mock_load_centre_collect: MagicMock,
    bluesky_context: BlueskyContext,
    load_centre_collect_params: LoadCentreCollect,
    udc_runner: PlanRunner,
):
    mock_load_centre_collect.side_effect = [
        WarningException(),
        MagicMock(),
        ValueError(),
    ]
    agamemnon.return_value = [load_centre_collect_params]
    with pytest.raises(PlanException) as e:
        run_udc_when_requested(bluesky_context, udc_runner)

    assert isinstance(e.value.__cause__, ValueError)
    baton = find_device_in_context(bluesky_context, "baton", Baton)
    assert mock_load_centre_collect.call_count == 3
    await _assert_baton_released(baton)


@patch("mx_bluesky.hyperion.baton_handler._move_to_default_state")
async def test_when_exception_raised_in_default_state_then_baton_released(
    default_state: MagicMock,
    bluesky_context: BlueskyContext,
    udc_runner: PlanRunner,
):
    default_state.side_effect = [ValueError()]
    with pytest.raises(ValueError):
        run_udc_when_requested(bluesky_context, udc_runner)

    baton = find_device_in_context(bluesky_context, "baton", Baton)
    await _assert_baton_released(baton)


@patch("mx_bluesky.hyperion.baton_handler.create_parameters_from_agamemnon")
async def test_when_exception_raised_in_getting_agamemnon_instruction_then_loop_stops_and_baton_released(
    agamemnon: MagicMock,
    udc_runner: PlanRunner,
    bluesky_context: BlueskyContext,
    RE: RunEngine,
):
    agamemnon.side_effect = ValueError()
    with pytest.raises(ValueError):
        run_udc_when_requested(bluesky_context, udc_runner)

    baton = find_device_in_context(bluesky_context, "baton", Baton)
    await _assert_baton_released(baton)


@patch("mx_bluesky.hyperion.baton_handler.create_parameters_from_agamemnon")
@patch("mx_bluesky.hyperion.baton_handler.load_centre_collect_full")
async def test_when_no_agamemnon_instructions_left_then_loop_stops_and_baton_released(
    collection: MagicMock,
    agamemnon: MagicMock,
    bluesky_context: BlueskyContext,
    udc_runner: PlanRunner,
):
    agamemnon.return_value = None
    run_udc_when_requested(bluesky_context, udc_runner)

    baton = find_device_in_context(bluesky_context, "baton", Baton)
    collection.assert_not_called()
    await _assert_baton_released(baton)


@patch("mx_bluesky.hyperion.baton_handler.create_parameters_from_agamemnon")
async def test_when_other_user_requested_collection_finished_then_baton_released(
    agamemnon: MagicMock,
    bluesky_context: BlueskyContext,
    mock_load_centre_collect: MagicMock,
    load_centre_collect_params: LoadCentreCollect,
    udc_runner: PlanRunner,
):
    plan_continuing = MagicMock()
    agamemnon.return_value = [load_centre_collect_params]

    def fake_collection_with_baton_request_part_way_through(*args):
        baton = find_device_in_context(bluesky_context, "baton", Baton)
        yield from bps.null()
        yield from bps.mv(baton.requested_user, "OTHER_USER")
        plan_continuing()

    mock_load_centre_collect.side_effect = (
        fake_collection_with_baton_request_part_way_through
    )

    run_udc_when_requested(bluesky_context, udc_runner)
    baton = find_device_in_context(bluesky_context, "baton", Baton)
    mock_load_centre_collect.assert_called_once()
    plan_continuing.assert_called_once()
    await _assert_baton_released(baton)
    assert await baton.requested_user.get_value() == "OTHER_USER"


@patch("mx_bluesky.hyperion.baton_handler.create_parameters_from_agamemnon")
@patch("mx_bluesky.hyperion.baton_handler._move_to_default_state")
async def test_when_multiple_agamemnon_instructions_then_default_state_only_run_once(
    default_state: MagicMock,
    agamemnon: MagicMock,
    mock_load_centre_collect: MagicMock,
    bluesky_context: BlueskyContext,
    udc_runner: PlanRunner,
):
    agamemnon.side_effect = [MagicMock(), MagicMock(), None]
    run_udc_when_requested(bluesky_context, udc_runner)
    default_state.assert_called_once()


@patch.dict(os.environ, {"BEAMLINE": "i03"})
def test_initialise_udc_reloads_all_devices():
    context = setup_context(True)
    devices_before_reset: LoadCentreCollectComposite = device_composite_from_context(
        context, LoadCentreCollectComposite
    )

    _initialise_udc(context)

    devices_after_reset: LoadCentreCollectComposite = device_composite_from_context(
        context, LoadCentreCollectComposite
    )

    for f in fields(devices_after_reset):
        device_after_reset = getattr(devices_after_reset, f.name)
        device_before_reset = getattr(devices_before_reset, f.name)
        assert device_before_reset is not device_after_reset, (
            f"{id(device_before_reset)} == {id(device_after_reset)}"
        )


@patch(
    "mx_bluesky.hyperion.baton_handler.create_parameters_from_agamemnon",
    MagicMock(
        side_effect=[
            [
                Wait.model_validate(
                    {"duration_s": 12.34, "parameter_model_version": PARAMETER_VERSION}
                )
            ],
            [],
        ]
    ),
)
def test_baton_handler_loop_waits_if_wait_instruction_received(
    bluesky_context_with_sim_run_engine: tuple[list[Msg], BlueskyContext],
    sim_run_engine: RunEngineSimulator,
):
    msgs, context = bluesky_context_with_sim_run_engine
    udc_runner = PlanRunner(context)
    run_udc_when_requested(context, udc_runner)

    assert_message_and_return_remaining(
        msgs, lambda msg: msg.command == "sleep" and msg.args[0] == 12.34
    )


def test_main_loop_rejects_unrecognised_instruction_when_received(
    bluesky_context_with_sim_run_engine: tuple[list[Msg], BlueskyContext],
    sim_run_engine: RunEngineSimulator,
):
    msgs, context = bluesky_context_with_sim_run_engine
    with (
        pytest.raises(AssertionError, match="Unsupported instruction decoded"),
        patch(
            "mx_bluesky.hyperion.baton_handler.create_parameters_from_agamemnon",
            MagicMock(
                side_effect=[
                    [
                        MxBlueskyParameters.model_validate(
                            {"parameter_model_version": PARAMETER_VERSION}
                        )
                    ],
                    [],
                ]
            ),
        ),
    ):
        run_udc_when_requested(context, PlanRunner(context))


async def test_shutdown_releases_the_baton(
    mock_create_params_from_agamemnon: MagicMock,
    udc_runner: PlanRunner,
    RE: RunEngine,
):
    mock_create_params_from_agamemnon.return_value = [
        Wait(duration_s=10, parameter_model_version=PARAMETER_VERSION)  # type: ignore
    ]

    async def wait_and_then_shutdown():
        while udc_runner.current_status != Status.BUSY:
            await sleep(0.1)
        udc_runner.shutdown()

    shutdown_task = run_coroutine_threadsafe(wait_and_then_shutdown(), RE.loop)

    run_forever(udc_runner)
    baton = find_device_in_context(udc_runner.context, "baton", Baton)
    await _assert_baton_released(baton)
    assert shutdown_task.done()


def _launch_test_in_runner_event_loop(async_func, udc_runner, executor) -> Future:
    """Launch the async func in a separate thread because the RunEngine under
    test must run in the main thread and block our test code, and return
    result and any exception to the caller."""

    def _launch_in_new_thread():
        future = asyncio.run_coroutine_threadsafe(async_func(), udc_runner.RE.loop)
        return future.result()

    return executor.submit(_launch_in_new_thread)


@patch(
    "mx_bluesky.hyperion.baton_handler.create_parameters_from_agamemnon",
    side_effect=[
        [
            Wait.model_validate(
                {"duration_s": 0.3, "parameter_model_version": PARAMETER_VERSION}
            )
        ],
        [
            Wait.model_validate(
                {"duration_s": 0.3, "parameter_model_version": PARAMETER_VERSION}
            )
        ],
    ],
)
@pytest.mark.timeout(1)
async def test_run_forever_resumes_collection_when_baton_taken_away(
    mock_create_parameters_from_agamemnon: MagicMock,
    udc_runner: PlanRunner,
    executor: Executor,
):
    async def take_requested_baton_away_then_wait_for_release_then_re_request():
        while udc_runner.current_status != Status.BUSY:
            await sleep(0.1)
        baton = find_device_in_context(udc_runner.context, "baton", Baton)
        await baton.requested_user.set(NO_USER)
        while await baton.current_user.get_value() != NO_USER:
            await sleep(0.1)
        assert len(mock_create_parameters_from_agamemnon.mock_calls) == 1
        await baton.requested_user.set(HYPERION_USER)
        while udc_runner.current_status != Status.BUSY:
            await sleep(0.1)
        udc_runner.shutdown()

    future = _launch_test_in_runner_event_loop(
        take_requested_baton_away_then_wait_for_release_then_re_request,
        udc_runner,
        executor,
    )
    run_forever(udc_runner)

    future.result()  # Ensure successful completion
    assert len(mock_create_parameters_from_agamemnon.mock_calls) == 2


@patch(
    "mx_bluesky.hyperion.baton_handler.create_parameters_from_agamemnon",
    side_effect=[
        [
            Wait.model_validate(
                {"duration_s": 0.3, "parameter_model_version": PARAMETER_VERSION}
            )
        ],
        [],
        [
            Wait.model_validate(
                {"duration_s": 0.3, "parameter_model_version": PARAMETER_VERSION}
            )
        ],
    ],
)
@pytest.mark.timeout(1)
async def test_run_forever_resumes_collection_when_normal_completion_and_baton_returned(
    mock_create_parameters_from_agamemnon: MagicMock,
    udc_runner: PlanRunner,
    executor: Executor,
):
    async def wait_for_baton_release_then_re_request():
        while udc_runner.current_status != Status.BUSY:
            await sleep(0.1)
        baton = find_device_in_context(udc_runner.context, "baton", Baton)
        while await baton.current_user.get_value() != NO_USER:
            await sleep(0.1)
        assert len(mock_create_parameters_from_agamemnon.mock_calls) == 2
        await baton.requested_user.set(HYPERION_USER)
        while udc_runner.current_status != Status.BUSY:
            await sleep(0.1)
        udc_runner.shutdown()

    future = _launch_test_in_runner_event_loop(
        wait_for_baton_release_then_re_request, udc_runner, executor
    )
    run_forever(udc_runner)

    future.result()  # Ensure successful completion
    assert len(mock_create_parameters_from_agamemnon.mock_calls) == 3


@patch(
    "mx_bluesky.hyperion.baton_handler.create_parameters_from_agamemnon",
    side_effect=AssertionError("Runner started command processing without baton"),
)
def test_run_forever_handles_shutdown_while_waiting_for_baton(
    mock_create_parameters_from_agamemnon: MagicMock,
    udc_runner: PlanRunner,
    executor: Executor,
):
    async def issue_shutdown_without_baton():
        baton = find_device_in_context(udc_runner.context, "baton", Baton)
        await baton.requested_user.set(NO_USER)
        await sleep(0.1)
        assert udc_runner.current_status == Status.IDLE
        udc_runner.shutdown()

    future = _launch_test_in_runner_event_loop(
        issue_shutdown_without_baton, udc_runner, executor
    )
    run_forever(udc_runner)
    future.result()  # Ensure successful completion


@patch(
    "mx_bluesky.hyperion.baton_handler.create_parameters_from_agamemnon",
    side_effect=[
        [
            Wait.model_validate(
                {"duration_s": 0.3, "parameter_model_version": PARAMETER_VERSION}
            )
        ],
        [
            Wait.model_validate(
                {"duration_s": 0.3, "parameter_model_version": PARAMETER_VERSION}
            )
        ],
        [],
    ],
)
def test_run_forever_clears_error_status_on_resume(
    mock_create_parameters_from_agamemnon: MagicMock,
    udc_runner: PlanRunner,
    executor: Executor,
):
    async def error_with_command_then_resume():
        with patch(
            "mx_bluesky.hyperion.baton_handler._runner_sleep",
            side_effect=RuntimeError("Simulated plan exception"),
        ):
            while udc_runner.current_status != Status.FAILED:
                await sleep(0.1)
        assert len(mock_create_parameters_from_agamemnon.mock_calls) == 1
        baton = find_device_in_context(udc_runner.context, "baton", Baton)
        while await baton.current_user.get_value() != NO_USER:
            await sleep(0.1)
        await baton.requested_user.set(HYPERION_USER)
        while udc_runner.current_status != Status.BUSY:
            await sleep(0.1)
        udc_runner.shutdown()

    future = _launch_test_in_runner_event_loop(
        error_with_command_then_resume, udc_runner, executor
    )
    run_forever(udc_runner)

    future.result()  # Ensure successful completion
