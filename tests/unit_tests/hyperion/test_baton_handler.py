import os
from asyncio import run_coroutine_threadsafe, sleep
from concurrent.futures import Executor
from contextlib import nullcontext
from dataclasses import fields
from threading import Event
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest
from blueapi.core import BlueskyContext
from bluesky import Msg
from bluesky import plan_stubs as bps
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from dodal.devices.baton import Baton
from dodal.devices.xbpm_feedback import XBPMFeedback
from dodal.utils import get_beamline_based_on_environment_variable
from ophyd_async.testing import get_mock_put, set_mock_value

from mx_bluesky.common.device_setup_plans.xbpm_feedback import (
    IGNORE_FEEDBACK_THRESHOLD_PC,
)
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
from mx_bluesky.common.utils.log import LOGGER
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
from mx_bluesky.hyperion.external_interaction.alerting.constants import Subjects
from mx_bluesky.hyperion.parameters.components import Wait
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect
from mx_bluesky.hyperion.plan_runner import PlanException, PlanRunner
from mx_bluesky.hyperion.utils.context import setup_context

from .conftest import launch_test_in_runner_event_loop

# For tests to complete reliably, these should all be successively much
# larger than each other

# Time to wait in test script between checks for a generic condition
SLEEP_FAST_SPIN_WAIT_S = 0.02
# Time to wait for the test to progress to the next step
AGAMEMNON_WAIT_FOR_TEST_STEP_S = 0.2
# Time for pytest to timeout if the script thread is deadlocked (shouldn't need this)
# PYTEST_TEST_TIMEOUT_S > TEST_SCRIPT_TIMEOUT in order that an exception on the script
# is bubbled up via the future and not lost.
PYTEST_TEST_TIMEOUT_S = 10

AGAMEMNON_WAIT_INSTRUCTION = Wait.model_validate(
    {
        "duration_s": AGAMEMNON_WAIT_FOR_TEST_STEP_S,
        "parameter_model_version": PARAMETER_VERSION,
    }
)


@pytest.fixture(autouse=True)
def patch_setup_devices(request):
    """
    Patch setup_devices() so that it doesn't rebuild all the devices
    if they already exist.
    """
    from mx_bluesky.hyperion.utils.context import setup_devices

    def patched_setup_devices(context: BlueskyContext, dev_mode: bool):
        if isinstance(context.run_engine, MagicMock):
            # We are using the sim run engine, device state doesn't matter
            setup_devices(context, True)
        else:
            try:
                find_device_in_context(context, "baton", Baton)
                # If we found a baton, leave devices alone and do nothing
            except ValueError:
                # No baton, setup devices and configure it
                setup_devices(context, True)
                baton_with_requested_user(context, HYPERION_USER)

    with (
        patch(
            "mx_bluesky.hyperion.baton_handler.setup_devices",
            side_effect=patched_setup_devices,
        ) as patched_func,
        nullcontext()
        if "dont_patch_clear_devices" in request.fixturenames
        else patch("mx_bluesky.hyperion.baton_handler.clear_all_device_caches"),
    ):
        yield patched_func


@pytest.fixture
def dont_patch_clear_devices():
    return


@pytest.fixture
def bluesky_context(RE: RunEngine, use_beamline_t01):
    # Baton for real run engine

    # Set the initial baton state
    context = BlueskyContext(RE)
    context.with_dodal_module(
        get_beamline_based_on_environment_variable(),
        mock=True,
        fake_with_ophyd_sim=True,
    )

    baton_with_requested_user(context, HYPERION_USER)
    yield context


@pytest.fixture
def bluesky_context_with_sim_run_engine(sim_run_engine: RunEngineSimulator):
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

    msgs = []

    def run_plan_in_sim(plan):
        msgs.extend(sim_run_engine.simulate_plan(plan))
        return sim_run_engine.return_value

    faked_run_engine = MagicMock(spec=RunEngine, side_effect=run_plan_in_sim)  # type: ignore

    # wait_for_connection in ensure_connected creates a bunch of awaitables
    # that will never be awaited by the simulator, let's not create them
    def dont_connect(*args, **kwargs):
        yield from bps.null()

    with (
        patch("blueapi.utils.connect_devices.ensure_connected", dont_connect),
        patch.dict(os.environ, {"BEAMLINE": "i03"}),
    ):
        context = BlueskyContext(faked_run_engine)
        context.with_dodal_module(
            get_beamline_based_on_environment_variable(),
            mock=True,
            fake_with_ophyd_sim=True,
        )
        yield msgs, context


def baton_with_requested_user(
    bluesky_context: BlueskyContext, user: str = HYPERION_USER
) -> Baton:
    baton = find_device_in_context(bluesky_context, "baton", Baton)
    set_mock_value(baton.requested_user, user)
    return baton


@pytest.fixture()
def udc_runner(bluesky_context: BlueskyContext, RE: RunEngine) -> PlanRunner:
    return PlanRunner(bluesky_context)


@pytest.fixture
def mock_load_centre_collect():
    with (
        patch("mx_bluesky.hyperion.baton_handler.create_devices"),
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


@patch("mx_bluesky.hyperion.baton_handler._move_to_udc_default_state", new=MagicMock())
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


@patch("mx_bluesky.hyperion.baton_handler._move_to_udc_default_state", new=MagicMock())
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


@patch("mx_bluesky.hyperion.baton_handler._move_to_udc_default_state")
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
    assert parent_mock.method_calls == [
        call.default_state(bluesky_context),
        call.main_loop(),
    ]


async def _assert_baton_released(baton: Baton):
    assert await baton.requested_user.get_value() != HYPERION_USER
    assert get_mock_put(baton.current_user).mock_calls[-1] == call(NO_USER, wait=True)


@patch("mx_bluesky.hyperion.baton_handler.create_parameters_from_agamemnon")
@patch("mx_bluesky.hyperion.baton_handler._move_to_udc_default_state", new=MagicMock())
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
@patch("mx_bluesky.hyperion.baton_handler._move_to_udc_default_state", new=MagicMock())
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


@patch("mx_bluesky.hyperion.baton_handler._move_to_udc_default_state")
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
@patch("mx_bluesky.hyperion.baton_handler._move_to_udc_default_state", new=MagicMock())
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
@patch("mx_bluesky.hyperion.baton_handler._move_to_udc_default_state", new=MagicMock())
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
@patch("mx_bluesky.hyperion.baton_handler._move_to_udc_default_state", new=MagicMock())
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
@patch("mx_bluesky.hyperion.baton_handler._move_to_udc_default_state")
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
def test_initialise_udc_reloads_all_devices(dont_patch_clear_devices):
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


@patch("mx_bluesky.hyperion.baton_handler._move_to_udc_default_state", new=MagicMock())
@pytest.mark.timeout(PYTEST_TEST_TIMEOUT_S)
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


@patch(
    "mx_bluesky.hyperion.baton_handler.create_parameters_from_agamemnon",
    side_effect=[
        [AGAMEMNON_WAIT_INSTRUCTION],
        [AGAMEMNON_WAIT_INSTRUCTION],
        AssertionError(
            "create_parameters_from_agamemnon was unexpectedly called a 3rd time"
        ),
    ],
)
@patch("mx_bluesky.hyperion.baton_handler._move_to_udc_default_state", new=MagicMock())
@pytest.mark.timeout(PYTEST_TEST_TIMEOUT_S)
async def test_run_forever_resumes_collection_when_baton_taken_away(
    mock_create_parameters_from_agamemnon: MagicMock,
    udc_runner: PlanRunner,
    executor: Executor,
):
    async def take_requested_baton_away_then_wait_for_release_then_re_request():
        while udc_runner.current_status != Status.BUSY:
            await sleep(SLEEP_FAST_SPIN_WAIT_S)
        try:
            baton = find_device_in_context(udc_runner.context, "baton", Baton)
            # un-request baton, hyperion should have processed first instruction
            await baton.requested_user.set(NO_USER)
            while await baton.current_user.get_value() != NO_USER:
                await sleep(SLEEP_FAST_SPIN_WAIT_S)
            assert len(mock_create_parameters_from_agamemnon.mock_calls) == 1
            # Re-request baton, wait until hyperion picks up baton
            await baton.requested_user.set(HYPERION_USER)
            while udc_runner.current_status != Status.BUSY:
                await sleep(SLEEP_FAST_SPIN_WAIT_S)
        finally:
            udc_runner.shutdown()

    future = launch_test_in_runner_event_loop(
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
        [AGAMEMNON_WAIT_INSTRUCTION],
        [],
        [AGAMEMNON_WAIT_INSTRUCTION],
    ],
)
@patch("mx_bluesky.hyperion.baton_handler._move_to_udc_default_state", new=MagicMock())
@pytest.mark.timeout(PYTEST_TEST_TIMEOUT_S)
async def test_run_forever_resumes_collection_when_normal_completion_and_baton_returned(
    mock_create_parameters_from_agamemnon: MagicMock,
    udc_runner: PlanRunner,
    executor: Executor,
):
    async def wait_for_baton_release_then_re_request():
        try:
            while udc_runner.current_status != Status.BUSY:
                await sleep(SLEEP_FAST_SPIN_WAIT_S)
            baton = find_device_in_context(udc_runner.context, "baton", Baton)
            while await baton.current_user.get_value() != NO_USER:
                await sleep(SLEEP_FAST_SPIN_WAIT_S)
            assert len(mock_create_parameters_from_agamemnon.mock_calls) == 2
            await baton.requested_user.set(HYPERION_USER)
            while udc_runner.current_status != Status.BUSY:
                await sleep(SLEEP_FAST_SPIN_WAIT_S)
        finally:
            udc_runner.shutdown()

    future = launch_test_in_runner_event_loop(
        wait_for_baton_release_then_re_request, udc_runner, executor
    )
    run_forever(udc_runner)

    future.result()  # Ensure successful completion
    assert len(mock_create_parameters_from_agamemnon.mock_calls) == 3


@patch(
    "mx_bluesky.hyperion.baton_handler.create_parameters_from_agamemnon",
    side_effect=AssertionError("Runner started command processing without baton"),
)
@patch("mx_bluesky.hyperion.baton_handler._move_to_udc_default_state", new=MagicMock())
async def test_run_forever_handles_shutdown_while_waiting_for_baton(
    mock_create_parameters_from_agamemnon: MagicMock,
    udc_runner: PlanRunner,
    executor: Executor,
):
    baton = find_device_in_context(udc_runner.context, "baton", Baton)
    await baton.requested_user.set(NO_USER)

    async def issue_shutdown_without_baton():
        try:
            await sleep(0.1)
            assert udc_runner.current_status == Status.IDLE
        finally:
            udc_runner.shutdown()

    future = launch_test_in_runner_event_loop(
        issue_shutdown_without_baton, udc_runner, executor
    )
    run_forever(udc_runner)
    future.result()  # Ensure successful completion


@pytest.mark.timeout(PYTEST_TEST_TIMEOUT_S)
@patch(
    "mx_bluesky.hyperion.baton_handler.create_parameters_from_agamemnon",
    side_effect=[
        [AGAMEMNON_WAIT_INSTRUCTION],
        [AGAMEMNON_WAIT_INSTRUCTION],
        [],
    ],
)
@patch("mx_bluesky.hyperion.baton_handler._move_to_udc_default_state", new=MagicMock())
def test_run_forever_clears_error_status_on_resume(
    mock_create_parameters_from_agamemnon: MagicMock,
    udc_runner: PlanRunner,
    executor: Executor,
):
    function_is_patched = Event()

    async def error_with_command_then_resume():
        with patch(
            "mx_bluesky.hyperion.baton_handler._runner_sleep",
            side_effect=RuntimeError("Simulated plan exception"),
        ):
            function_is_patched.set()
            while udc_runner.current_status != Status.FAILED:
                await sleep(SLEEP_FAST_SPIN_WAIT_S)
        assert len(mock_create_parameters_from_agamemnon.mock_calls) == 1
        baton = find_device_in_context(udc_runner.context, "baton", Baton)
        while await baton.current_user.get_value() != NO_USER:
            await sleep(SLEEP_FAST_SPIN_WAIT_S)
        await baton.requested_user.set(HYPERION_USER)
        while udc_runner.current_status != Status.BUSY:
            await sleep(SLEEP_FAST_SPIN_WAIT_S)
        udc_runner.shutdown()

    future = launch_test_in_runner_event_loop(
        error_with_command_then_resume, udc_runner, executor
    )
    function_is_patched.wait()
    run_forever(udc_runner)

    future.result()  # Ensure successful completion


@patch(
    "mx_bluesky.hyperion.baton_handler.create_parameters_from_agamemnon",
    side_effect=[
        [AGAMEMNON_WAIT_INSTRUCTION],
        [],
    ],
)
def test_feedback_wrapper_invoked_around_collection_loop_when_commissioning_mode_enabled(
    mock_create_parameters_from_agamemnon: MagicMock,
    udc_runner: PlanRunner,
    executor: Executor,
):
    parent = MagicMock()
    parent.attach_mock(
        mock_create_parameters_from_agamemnon, "create_parameters_from_agamemnon"
    )
    feedback = find_device_in_context(udc_runner.context, "xbpm_feedback", XBPMFeedback)
    parent.attach_mock(get_mock_put(feedback.threshold_pc), "threshold_pc")
    baton = find_device_in_context(udc_runner.context, "baton", Baton)
    set_mock_value(baton.commissioning, True)
    set_mock_value(feedback.threshold_pc, 3)

    async def wait_to_finish_then_shutdown():
        while len(mock_create_parameters_from_agamemnon.mock_calls) != 2:
            await sleep(SLEEP_FAST_SPIN_WAIT_S)

        udc_runner.shutdown()
        parent.assert_has_calls(
            [
                call.threshold_pc(IGNORE_FEEDBACK_THRESHOLD_PC, wait=True),
                call.create_parameters_from_agamemnon(),
                call.create_parameters_from_agamemnon(),
                call.threshold_pc(3, wait=True),
            ]
        )

    future = launch_test_in_runner_event_loop(
        wait_to_finish_then_shutdown, udc_runner, executor
    )
    run_forever(udc_runner)
    future.result()  # Ensure successful completion


@patch(
    "mx_bluesky.hyperion.baton_handler.create_parameters_from_agamemnon",
    side_effect=[
        [AGAMEMNON_WAIT_INSTRUCTION],
        [],
    ],
)
@patch("mx_bluesky.hyperion.baton_handler.set_commissioning_signal")
async def test_commissioning_signal_set_on_baton_acquire(
    mock_set_commissioning_signal: MagicMock,
    mock_create_parameters_from_agamemnon: MagicMock,
    udc_runner: PlanRunner,
    executor: Executor,
):
    baton = find_device_in_context(udc_runner.context, "baton", Baton)
    parent = MagicMock()
    parent.attach_mock(mock_set_commissioning_signal, "set_commissioning_signal")
    parent.attach_mock(get_mock_put(baton.current_user), "current_user")
    parent.attach_mock(
        mock_create_parameters_from_agamemnon, "create_parameters_from_agamemnon"
    )
    LOGGER.debug("Set no requested user")
    set_mock_value(baton.requested_user, NO_USER)

    async def release_baton_and_check_commissioning_signal_set():
        try:
            mock_set_commissioning_signal.assert_not_called()
            LOGGER.debug("Set requested user")
            set_mock_value(baton.requested_user, HYPERION_USER)
            LOGGER.debug("Wait for create_parameters call")
            while len(parent.create_parameters_from_agamemnon.mock_calls) == 0:
                await sleep(SLEEP_FAST_SPIN_WAIT_S)
            LOGGER.debug("Wait for idle")
            while udc_runner.current_status != Status.IDLE:
                await sleep(SLEEP_FAST_SPIN_WAIT_S)
            parent.assert_has_calls(
                [
                    call.current_user("Hyperion", wait=True),
                    call.set_commissioning_signal(baton.commissioning),
                    call.create_parameters_from_agamemnon(),
                    call.create_parameters_from_agamemnon(),
                ]
            )
        finally:
            LOGGER.debug("shutdown runner")
            udc_runner.shutdown()

    future = launch_test_in_runner_event_loop(
        release_baton_and_check_commissioning_signal_set, udc_runner, executor
    )
    run_forever(udc_runner)
    future.result()  # Ensure successful completion


@patch(
    "mx_bluesky.hyperion.baton_handler.create_parameters_from_agamemnon",
    MagicMock(side_effect=[[AGAMEMNON_WAIT_INSTRUCTION], []]),
)
@patch("mx_bluesky.hyperion.baton_handler._move_to_udc_default_state", new=MagicMock())
@patch("mx_bluesky.hyperion.baton_handler.get_alerting_service")
def test_run_udc_when_requested_raises_udc_start_alert_when_baton_acquired(
    mock_get_alerting_service: MagicMock,
    bluesky_context: BlueskyContext,
    udc_runner: PlanRunner,
):
    mock_alert_service = mock_get_alerting_service.return_value
    run_udc_when_requested(bluesky_context, udc_runner)

    assert mock_alert_service.raise_alert.mock_calls[0] == call(
        Subjects.UDC_STARTED, "Unattended Data Collection has started.", {}
    )


@patch("mx_bluesky.hyperion.baton_handler.create_parameters_from_agamemnon")
@patch("mx_bluesky.hyperion.baton_handler._move_to_udc_default_state", new=MagicMock())
@patch("mx_bluesky.hyperion.baton_handler.clear_all_device_caches", MagicMock())
@patch("mx_bluesky.hyperion.baton_handler.get_alerting_service")
def test_run_udc_when_requested_raises_baton_release_udc_completed_event_when_hyperion_releases_the_baton(
    mock_get_alerting_service: MagicMock,
    mock_create_params: MagicMock,
    bluesky_context: BlueskyContext,
    udc_runner: PlanRunner,
):
    parent = MagicMock()

    def wait_then_nothing():
        yield [AGAMEMNON_WAIT_INSTRUCTION]

        mock_alert_service = mock_get_alerting_service.return_value
        parent.attach_mock(mock_alert_service.raise_alert, "raise_alert")
        baton = find_device_in_context(bluesky_context, "baton", Baton)
        parent.attach_mock(get_mock_put(baton.current_user), "current_user")
        yield []

    mock_create_params.side_effect = wait_then_nothing()

    run_udc_when_requested(bluesky_context, udc_runner)

    parent.assert_has_calls(
        [
            call.raise_alert(
                Subjects.UDC_COMPLETED,
                "Hyperion UDC has completed all pending Agamemnon requests.",
                {},
            ),
            call.current_user(NO_USER, wait=True),
            call.raise_alert(
                Subjects.UDC_BATON_RELEASED,
                "Hyperion has released the baton. The baton is currently "
                "requested by: None",
                {},
            ),
        ]
    )


@patch("mx_bluesky.hyperion.baton_handler.create_parameters_from_agamemnon")
@patch("mx_bluesky.hyperion.baton_handler._move_to_udc_default_state", new=MagicMock())
@patch("mx_bluesky.hyperion.baton_handler.clear_all_device_caches", MagicMock())
@patch("mx_bluesky.hyperion.baton_handler.get_alerting_service")
def test_run_udc_when_requested_raises_baton_release_event_when_baton_requested_from_hyperion(
    mock_get_alerting_service: MagicMock,
    mock_create_params: MagicMock,
    bluesky_context: BlueskyContext,
    udc_runner: PlanRunner,
):
    parent = MagicMock()

    def wait_then_nothing():
        yield [AGAMEMNON_WAIT_INSTRUCTION]
        baton = find_device_in_context(bluesky_context, "baton", Baton)
        set_mock_value(baton.requested_user, "GDA")
        mock_alert_service = mock_get_alerting_service.return_value
        parent.attach_mock(mock_alert_service.raise_alert, "raise_alert")
        parent.attach_mock(get_mock_put(baton.current_user), "current_user")
        yield [AGAMEMNON_WAIT_INSTRUCTION]
        raise AssertionError(
            "This should never be reached as the baton has already been released."
        )

    mock_create_params.side_effect = wait_then_nothing()

    run_udc_when_requested(bluesky_context, udc_runner)

    parent.assert_has_calls(
        [
            call.current_user(NO_USER, wait=True),
            call.raise_alert(
                Subjects.UDC_BATON_RELEASED,
                "Hyperion has released the baton. The baton is currently "
                "requested by: GDA",
                {},
            ),
        ]
    )
