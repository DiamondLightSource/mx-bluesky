from typing import AsyncGenerator
from unittest.mock import ANY, MagicMock, call

import pytest
from bluesky.run_engine import RunEngine
from dodal.beamlines import i04
from dodal.devices.oav.oav_parameters import OAVConfigParams
from dodal.devices.oav.ophyd_async_oav import OAV, ZoomLevel
from dodal.devices.smargon import Smargon
from dodal.devices.thawer import Thawer, ThawerStates
from ophyd.sim import NullStatus
from ophyd_async.core import (
    DeviceCollector,
    callback_on_mock_put,
    get_mock_put,
    set_mock_value,
)
from ophyd_async.epics.motion import Motor

from mx_bluesky.i04.thawing_plan import thaw, thaw_and_center

DISPLAY_CONFIGURATION = "tests/devices/unit_tests/test_display.configuration"
ZOOM_LEVELS_XML = "tests/devices/unit_tests/test_jCameraManZoomLevels.xml"


class MyException(Exception):
    pass


def patch_motor(motor: Motor, initial_position: float = 0):
    set_mock_value(motor.user_setpoint, initial_position)
    set_mock_value(motor.user_readback, initial_position)
    set_mock_value(motor.deadband, 0.001)
    set_mock_value(motor.motor_done_move, 1)
    set_mock_value(motor.velocity, 3)
    return callback_on_mock_put(
        motor.user_setpoint,
        lambda pos, *args, **kwargs: set_mock_value(motor.user_readback, pos),
    )


@pytest.fixture
async def smargon() -> AsyncGenerator[Smargon, None]:
    RunEngine()
    smargon = Smargon(name="smargon")
    await smargon.connect(mock=True)

    set_mock_value(smargon.omega.user_readback, 0.0)

    with patch_motor(smargon.omega):
        yield smargon


@pytest.fixture
async def thawer() -> Thawer:
    RunEngine()
    return i04.thawer(fake_with_ophyd_sim=True)


@pytest.fixture
async def oav() -> OAV:
    RunEngine()
    oav_params = OAVConfigParams(ZOOM_LEVELS_XML, DISPLAY_CONFIGURATION)
    with DeviceCollector(mock=True):
        oav = OAV("ophyd_async_oav", oav_params)
    set_mock_value(oav.zoom_controller.level, ZoomLevel.ONE)
    set_mock_value(oav.x_size, 1024)
    set_mock_value(oav.y_size, 768)
    return oav


def _do_thaw_and_confirm_cleanup(
    move_mock: MagicMock, smargon: Smargon, thawer: Thawer, do_thaw_func
):
    set_mock_value(smargon.omega.velocity, initial_velocity := 10)
    do_thaw_func()
    last_thawer_call = get_mock_put(thawer.control).call_args_list[-1]
    assert last_thawer_call == call(ThawerStates.OFF, wait=ANY, timeout=ANY)
    last_velocity_call = get_mock_put(smargon.omega.velocity).call_args_list[-1]
    assert last_velocity_call == call(initial_velocity, wait=ANY, timeout=ANY)


def test_given_thaw_succeeds_then_velocity_restored_and_thawer_turned_off(
    smargon: Smargon, thawer: Thawer
):
    def do_thaw_func():
        RE = RunEngine()
        RE(thaw(10, thawer=thawer, smargon=smargon))

    _do_thaw_and_confirm_cleanup(
        MagicMock(return_value=NullStatus()), smargon, thawer, do_thaw_func
    )


def test_given_moving_smargon_gives_error_then_velocity_restored_and_thawer_turned_off(
    smargon: Smargon, thawer: Thawer
):
    def do_thaw_func():
        RE = RunEngine()
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
    smargon: Smargon, thawer: Thawer, time, rotation, expected_speed
):
    RE = RunEngine()
    RE(thaw(time, rotation, thawer=thawer, smargon=smargon))
    first_velocity_call = get_mock_put(smargon.omega.velocity).call_args_list[0]
    assert first_velocity_call == call(expected_speed, wait=ANY, timeout=ANY)


@pytest.mark.parametrize(
    "start_pos, rotation, expected_end",
    [
        (0, 360, 360),
        (78, 100, 178),
        (0, -100, -100),
    ],
)
def test_given_different_rotations_then_motor_moved_relative(
    smargon: Smargon, thawer: Thawer, start_pos, rotation, expected_end
):
    set_mock_value(smargon.omega.user_readback, start_pos)
    RE = RunEngine()
    RE(thaw(10, rotation, thawer=thawer, smargon=smargon))
    assert get_mock_put(smargon.omega.user_setpoint).call_args_list == [
        call(expected_end, wait=ANY, timeout=ANY),
        call(start_pos, wait=ANY, timeout=ANY),
    ]


def test_murko_callback(smargon: Smargon, thawer: Thawer, oav: OAV):
    RE = RunEngine()
    RE(thaw_and_center(10, 360, thawer=thawer, smargon=smargon, oav=oav))
