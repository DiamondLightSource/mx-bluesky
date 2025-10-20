from collections.abc import AsyncGenerator
from functools import partial
from unittest.mock import ANY, AsyncMock, MagicMock, call, patch

import pytest
from bluesky.run_engine import RunEngine
from bluesky.simulators import assert_message_and_return_remaining
from bluesky.utils import MsgGenerator
from dodal.beamlines import i04
from dodal.devices.i04.murko_results import MurkoResultsDevice
from dodal.devices.oav.oav_detector import OAV, OAVBeamCentrePV, OAVConfig
from dodal.devices.oav.oav_to_redis_forwarder import OAVToRedisForwarder, Source
from dodal.devices.robot import BartRobot
from dodal.devices.smargon import Smargon
from dodal.devices.thawer import OnOff, Thawer
from dodal.testing import patch_all_motors
from ophyd.sim import NullStatus
from ophyd_async.core import completed_status, init_devices
from ophyd_async.testing import (
    get_mock_put,
    set_mock_value,
)

from mx_bluesky.beamlines.i04.thawing_plan import (
    thaw,
    thaw_and_murko_centre,
    thaw_and_stream_to_redis,
)

DISPLAY_CONFIGURATION = "tests/test_data/test_display.configuration"
ZOOM_LEVELS_XML = "tests/test_data/test_jCameraManZoomLevels.xml"


class MyException(Exception):
    pass


@pytest.fixture
async def oav(RE: RunEngine) -> OAV:
    oav_config = OAVConfig(ZOOM_LEVELS_XML)
    async with init_devices(mock=True, connect=True):
        oav = OAVBeamCentrePV("", config=oav_config, name="fake_oav")
    zoom_levels_list = ["1.0x", "2.0x", "5.0x"]
    oav.zoom_controller._get_allowed_zoom_levels = AsyncMock(
        return_value=zoom_levels_list
    )
    set_mock_value(oav.zoom_controller.level, "1.0x")
    set_mock_value(oav.grid_snapshot.x_size, 1024)
    set_mock_value(oav.grid_snapshot.y_size, 768)
    return oav


@pytest.fixture
async def smargon(RE: RunEngine) -> AsyncGenerator[Smargon, None]:
    smargon = Smargon(prefix="BL04I-MO-SGON-01:", name="smargon")
    await smargon.connect(mock=True)

    set_mock_value(smargon.omega.user_readback, 0.0)

    with patch_all_motors(smargon):
        yield smargon


@pytest.fixture
def thawer(RE: RunEngine) -> Thawer:
    return i04.thawer(connect_immediately=True, mock=True)


@pytest.fixture
@patch("dodal.devices.i04.murko_results.StrictRedis")
async def murko_results(mock_strict_redis: MagicMock) -> MurkoResultsDevice:
    murko_results = MurkoResultsDevice(name="murko_results")
    murko_results.trigger = MagicMock(side_effect=completed_status)
    murko_results.stage = MagicMock(side_effect=completed_status)
    murko_results.unstage = MagicMock(side_effect=completed_status)
    return murko_results


@pytest.fixture
async def oav_forwarder(RE: RunEngine) -> OAVToRedisForwarder:
    with init_devices(mock=True):
        oav_forwarder = OAVToRedisForwarder(
            "prefix", "host", "password", name="oav_to_redis_forwarder"
        )
    set_mock_value(oav_forwarder.uuid, "test")

    oav_forwarder.kickoff = MagicMock(side_effect=completed_status)
    oav_forwarder.complete = MagicMock(side_effect=completed_status)
    return oav_forwarder


@pytest.fixture
def robot(RE: RunEngine) -> BartRobot:
    return i04.robot(connect_immediately=True, mock=True)


def _do_thaw_and_confirm_cleanup(
    move_mock: MagicMock, smargon: Smargon, thawer: Thawer, do_thaw_func
):
    smargon.omega.set = move_mock
    set_mock_value(smargon.omega.velocity, initial_velocity := 10)
    smargon.omega.set = move_mock
    do_thaw_func()
    last_thawer_call = get_mock_put(thawer.control).call_args_list[-1]
    assert last_thawer_call == call(OnOff.OFF, wait=ANY)
    last_velocity_call = get_mock_put(smargon.omega.velocity).call_args_list[-1]
    assert last_velocity_call == call(initial_velocity, wait=ANY)


def test_given_thaw_succeeds_then_velocity_restored_and_thawer_turned_off(
    smargon: Smargon, thawer: Thawer, RE: RunEngine
):
    def do_thaw_func():
        RE(thaw(10, thawer=thawer, smargon=smargon))

    _do_thaw_and_confirm_cleanup(
        MagicMock(return_value=NullStatus()), smargon, thawer, do_thaw_func
    )


def test_given_moving_smargon_gives_error_then_velocity_restored_and_thawer_turned_off(
    smargon: Smargon, thawer: Thawer, RE: RunEngine
):
    def do_thaw_func():
        with pytest.raises(MyException):
            RE(thaw(10, thawer=thawer, smargon=smargon))

    _do_thaw_and_confirm_cleanup(
        MagicMock(side_effect=MyException()), smargon, thawer, do_thaw_func
    )


@pytest.mark.parametrize(
    "time, rotation, expected_speed",
    [
        (10, 360, 72),
        (3.5, 100, pytest.approx(57.142857)),
        (50, -100, 4),
    ],
)
def test_given_different_rotations_and_times_then_velocity_correct(
    smargon: Smargon,
    thawer: Thawer,
    time: float,
    rotation: float,
    expected_speed: float,
    RE: RunEngine,
):
    RE(thaw(time, rotation, thawer=thawer, smargon=smargon))
    first_velocity_call = get_mock_put(smargon.omega.velocity).call_args_list[0]
    assert first_velocity_call == call(expected_speed, wait=ANY)


@pytest.mark.parametrize(
    "start_pos, rotation, expected_end",
    [
        (0, 360, 360),
        (78, 100, 178),
        (0, -100, -100),
    ],
)
def test_given_different_rotations_then_motor_moved_relative(
    smargon: Smargon,
    thawer: Thawer,
    start_pos: float,
    rotation: float,
    expected_end: float,
    RE: RunEngine,
):
    set_mock_value(smargon.omega.user_setpoint, start_pos)
    RE(thaw(10, rotation, thawer=thawer, smargon=smargon))
    assert get_mock_put(smargon.omega.user_setpoint).call_args_list == [
        call(expected_end, wait=ANY),
        call(start_pos, wait=ANY),
    ]


@patch("mx_bluesky.beamlines.i04.thawing_plan.MurkoCallback")
async def test_thaw_and_stream_sets_sample_id_and_kicks_off_forwarder(
    patch_murko_callback: MagicMock,
    smargon: Smargon,
    thawer: Thawer,
    oav_forwarder: OAVToRedisForwarder,
    oav: OAV,
    robot: BartRobot,
    RE: RunEngine,
):
    set_mock_value(robot.sample_id, 100)
    RE(
        thaw_and_stream_to_redis(
            10,
            360,
            thawer=thawer,
            smargon=smargon,
            oav=oav,
            robot=robot,
            oav_to_redis_forwarder=oav_forwarder,
        )
    )
    assert await oav_forwarder.sample_id.get_value() == 100
    oav_forwarder.kickoff.assert_called()  # type: ignore
    oav_forwarder.complete.assert_called()  # type: ignore


@patch("mx_bluesky.beamlines.i04.thawing_plan.MurkoCallback")
def test_thaw_and_stream_adds_murko_callback_and_produces_expected_messages(
    patch_murko_callback: MagicMock,
    smargon: Smargon,
    thawer: Thawer,
    robot: BartRobot,
    oav_forwarder: OAVToRedisForwarder,
    oav: OAV,
    RE: RunEngine,
):
    patch_murko_instance = patch_murko_callback.return_value
    RE(
        thaw_and_stream_to_redis(
            10,
            360,
            thawer=thawer,
            smargon=smargon,
            oav=oav,
            robot=robot,
            oav_to_redis_forwarder=oav_forwarder,
        )
    )

    docs = patch_murko_instance.call_args_list
    start_params = [c.args[1] for c in docs if c.args[0] == "start"]
    event_params = [c.args[1] for c in docs if c.args[0] == "event"]
    assert len(start_params) == 1
    assert len(event_params) == 4
    oav_updates = [
        e for e in event_params if "oav_to_redis_forwarder-uuid" in e["data"].keys()
    ]
    smargon_updates = [e for e in event_params if "smargon-omega" in e["data"].keys()]
    assert len(oav_updates) > 0
    assert len(smargon_updates) > 0


@patch("mx_bluesky.beamlines.i04.thawing_plan.MurkoCallback.call_murko")
def test_thaw_and_stream_will_produce_events_that_call_murko(
    patch_murko_call: MagicMock,
    smargon: Smargon,
    thawer: Thawer,
    robot: BartRobot,
    oav_forwarder: OAVToRedisForwarder,
    oav: OAV,
    RE: RunEngine,
):
    RE(
        thaw_and_stream_to_redis(
            10,
            360,
            thawer=thawer,
            smargon=smargon,
            oav=oav,
            robot=robot,
            oav_to_redis_forwarder=oav_forwarder,
        )
    )
    patch_murko_call.assert_called()


def _test_plan_will_switch_murko_source_half_way_through_thaw(
    sim_run_engine, plan: MsgGenerator
):
    msgs = sim_run_engine.simulate_plan(plan)
    for source in [Source.FULL_SCREEN.value, Source.ROI.value]:
        msgs = assert_message_and_return_remaining(
            msgs,
            lambda msg: msg.command == "set"
            and msg.obj.name == "oav_to_redis_forwarder-selected_source"
            and msg.args[0] == source,
        )
        msgs = assert_message_and_return_remaining(
            msgs,
            lambda msg: msg.command == "kickoff"
            and msg.obj.name == "oav_to_redis_forwarder",
        )
        msgs = assert_message_and_return_remaining(
            msgs,
            lambda msg: msg.command == "set" and msg.obj.name == "smargon-omega",
        )
        msgs = assert_message_and_return_remaining(
            msgs,
            lambda msg: msg.command == "complete"
            and msg.obj.name == "oav_to_redis_forwarder",
        )


def test_thaw_and_stream_will_switch_murko_source_half_way_through_thaw(
    sim_run_engine,
    smargon: Smargon,
    thawer: Thawer,
    oav_forwarder: OAVToRedisForwarder,
    oav: OAV,
    robot: BartRobot,
):
    _test_plan_will_switch_murko_source_half_way_through_thaw(
        sim_run_engine,
        thaw_and_stream_to_redis(10, 360, robot, thawer, smargon, oav, oav_forwarder),
    )


def _run_thaw_and_stream_and_assert_zoom_changes(
    smargon: Smargon,
    thawer: Thawer,
    oav_forwarder: OAVToRedisForwarder,
    oav: OAV,
    robot: BartRobot,
    RE: RunEngine,
    expect_raises=None,
):
    set_mock_value(oav.zoom_controller.level, "2.0x")

    run_plan = partial(
        RE,
        thaw_and_stream_to_redis(
            10,
            360,
            thawer=thawer,
            smargon=smargon,
            oav=oav,
            robot=robot,
            oav_to_redis_forwarder=oav_forwarder,
        ),
    )

    if expect_raises:
        with pytest.raises(expect_raises):
            run_plan()
    else:
        run_plan()

    mock_level_set = get_mock_put(oav.zoom_controller.level)
    mock_level_set.assert_has_calls([call("1.0x", wait=True), call("2.0x", wait=True)])


@patch("mx_bluesky.beamlines.i04.thawing_plan.MurkoCallback")
def test_given_thaw_succeeds_then_thaw_and_stream_sets_zoom_to_1_and_back(
    patch_murko_callback,
    smargon: Smargon,
    thawer: Thawer,
    oav_forwarder: OAVToRedisForwarder,
    oav: OAV,
    robot: BartRobot,
    RE: RunEngine,
):
    _run_thaw_and_stream_and_assert_zoom_changes(
        smargon, thawer, oav_forwarder, oav, robot, RE
    )


@patch("mx_bluesky.beamlines.i04.thawing_plan.MurkoCallback")
@patch("mx_bluesky.beamlines.i04.thawing_plan._thaw")
def test_given_thaw_fails_then_thaw_and_stream_sets_zoom_to_1_and_back(
    mock__thaw,
    patch_murko_callback,
    smargon: Smargon,
    thawer: Thawer,
    oav_forwarder: OAVToRedisForwarder,
    oav: OAV,
    robot: BartRobot,
    RE: RunEngine,
):
    mock__thaw.side_effect = Exception()
    _run_thaw_and_stream_and_assert_zoom_changes(
        smargon, thawer, oav_forwarder, oav, robot, RE, Exception
    )


@patch("mx_bluesky.beamlines.i04.thawing_plan.MurkoCallback")
@patch("mx_bluesky.beamlines.i04.thawing_plan._thaw")
def test_thaw_and_murko_centre_stages_and_unstages_murko_results(
    mock__thaw,
    patch_murko_callback,
    smargon: Smargon,
    thawer: Thawer,
    oav_forwarder: OAVToRedisForwarder,
    oav: OAV,
    robot: BartRobot,
    murko_results: MurkoResultsDevice,
    RE: RunEngine,
):
    RE(
        thaw_and_murko_centre(
            10, 360, robot, thawer, smargon, oav, murko_results, oav_forwarder
        ),
    )

    murko_results.stage.assert_called_once()  # type: ignore
    murko_results.unstage.assert_called_once()  # type: ignore


@patch("mx_bluesky.beamlines.i04.thawing_plan.MurkoCallback")
@patch("mx_bluesky.beamlines.i04.thawing_plan._thaw")
def test_given_thaw_and_murko_centre_errors_then_murko_results_still_unstaged(
    mock__thaw,
    patch_murko_callback,
    smargon: Smargon,
    thawer: Thawer,
    oav_forwarder: OAVToRedisForwarder,
    oav: OAV,
    robot: BartRobot,
    murko_results: MurkoResultsDevice,
    RE: RunEngine,
):
    mock__thaw.side_effect = ValueError()

    with pytest.raises(ValueError):
        RE(
            thaw_and_murko_centre(
                10, 360, robot, thawer, smargon, oav, murko_results, oav_forwarder
            ),
        )

    murko_results.stage.assert_called_once()  # type: ignore
    murko_results.unstage.assert_called_once()  # type: ignore


def test_thaw_and_murko_centre_will_switch_murko_source_half_way_through_thaw(
    sim_run_engine,
    smargon: Smargon,
    thawer: Thawer,
    oav_forwarder: OAVToRedisForwarder,
    oav: OAV,
    robot: BartRobot,
    murko_results: MurkoResultsDevice,
):
    _test_plan_will_switch_murko_source_half_way_through_thaw(
        sim_run_engine,
        thaw_and_murko_centre(
            10, 360, robot, thawer, smargon, oav, murko_results, oav_forwarder
        ),
    )


@patch("mx_bluesky.beamlines.i04.thawing_plan.MurkoCallback")
def test_thaw_and_murko_centre_will_centre_based_on_murko_results_half_way_through_thaw(
    patch_murko_callback,
    RE,
    smargon: Smargon,
    thawer: Thawer,
    oav_forwarder: OAVToRedisForwarder,
    oav: OAV,
    robot: BartRobot,
    murko_results: MurkoResultsDevice,
):
    def fake_trigger():
        murko_results._x_mm_setter(1)
        murko_results._y_mm_setter(2)
        murko_results._z_mm_setter(3)
        return completed_status()

    murko_results.trigger = MagicMock(side_effect=fake_trigger)

    RE(
        thaw_and_murko_centre(
            10, 360, robot, thawer, smargon, oav, murko_results, oav_forwarder
        ),
    )

    get_mock_put(smargon.x.user_setpoint).assert_has_calls([call(1.0, wait=True)])
    get_mock_put(smargon.y.user_setpoint).assert_has_calls([call(2.0, wait=True)])
    get_mock_put(smargon.z.user_setpoint).assert_has_calls([call(3.0, wait=True)])


def test_thaw_and_murko_centre_will_set_sample_id_before_triggering_results(
    sim_run_engine,
    smargon: Smargon,
    thawer: Thawer,
    oav_forwarder: OAVToRedisForwarder,
    oav: OAV,
    robot: BartRobot,
    murko_results: MurkoResultsDevice,
):
    sim_run_engine.add_read_handler_for(robot.sample_id, "1234")

    msgs = sim_run_engine.simulate_plan(
        thaw_and_murko_centre(
            10, 360, robot, thawer, smargon, oav, murko_results, oav_forwarder
        )
    )

    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "murko_results-sample_id"
        and msg.args[0] == "1234",
    )
    msgs = assert_message_and_return_remaining(
        msgs, lambda msg: msg.command == "trigger" and msg.obj.name == "murko_results"
    )
