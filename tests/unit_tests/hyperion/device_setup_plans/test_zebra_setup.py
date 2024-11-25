from unittest.mock import MagicMock, call

import pytest
from bluesky import plan_stubs as bps
from bluesky.protocols import Movable
from dodal.devices.zebra import (
    AUTO_SHUTTER_GATE,
    AUTO_SHUTTER_INPUT_1,
    AUTO_SHUTTER_INPUT_2,
    IN1_TTL,
    IN3_TTL,
    IN4_TTL,
    PC_GATE,
    PC_PULSE,
    SOFT_IN1,
    TTL_DETECTOR,
    TTL_PANDA,
    I03Axes,
    Zebra,
)
from dodal.devices.zebra_controlled_shutter import ZebraShutter, ZebraShutterControl

from mx_bluesky.hyperion.device_setup_plans.setup_zebra import (
    bluesky_retry,
    configure_zebra_and_shutter_for_auto_shutter,
    setup_zebra_for_gridscan,
    setup_zebra_for_panda_flyscan,
    setup_zebra_for_rotation,
    tidy_up_zebra_after_gridscan,
)


async def _get_shutter_input_2(zebra: Zebra):
    return (
        await zebra.logic_gates.and_gates[AUTO_SHUTTER_GATE]
        .sources[AUTO_SHUTTER_INPUT_2]
        .get_value()
    )


async def _get_shutter_input_1(zebra: Zebra):
    return (
        await zebra.logic_gates.and_gates[AUTO_SHUTTER_GATE]
        .sources[AUTO_SHUTTER_INPUT_1]
        .get_value()
    )


async def test_zebra_set_up_for_panda_gridscan(
    RE, zebra: Zebra, zebra_shutter: ZebraShutter
):
    RE(setup_zebra_for_panda_flyscan(zebra, zebra_shutter, wait=True))
    assert await zebra.output.out_pvs[TTL_DETECTOR].get_value() == IN1_TTL
    assert await zebra.output.out_pvs[TTL_PANDA].get_value() == IN3_TTL
    assert await zebra_shutter.control_mode.get_value() == ZebraShutterControl.AUTO
    assert await _get_shutter_input_2(zebra) == IN4_TTL
    assert await _get_shutter_input_1(zebra) == SOFT_IN1


async def test_zebra_set_up_for_gridscan(RE, zebra: Zebra, zebra_shutter: ZebraShutter):
    RE(setup_zebra_for_gridscan(zebra, zebra_shutter, wait=True))
    assert await zebra.output.out_pvs[TTL_DETECTOR].get_value() == IN3_TTL
    assert await _get_shutter_input_2(zebra) == IN4_TTL
    assert await zebra_shutter.control_mode.get_value() == ZebraShutterControl.AUTO
    assert await _get_shutter_input_1(zebra) == SOFT_IN1


async def test_zebra_set_up_for_rotation(RE, zebra: Zebra, zebra_shutter: ZebraShutter):
    RE(setup_zebra_for_rotation(zebra, zebra_shutter, wait=True))
    assert await zebra.pc.gate_trigger.get_value() == I03Axes.OMEGA.value
    assert await zebra.pc.gate_width.get_value() == pytest.approx(360, 0.01)
    assert await zebra_shutter.control_mode.get_value() == ZebraShutterControl.AUTO
    assert await _get_shutter_input_1(zebra) == SOFT_IN1


async def test_zebra_cleanup(RE, zebra: Zebra, zebra_shutter: ZebraShutter):
    RE(tidy_up_zebra_after_gridscan(zebra, zebra_shutter, wait=True))
    assert await zebra.output.out_pvs[TTL_DETECTOR].get_value() == PC_PULSE
    assert await _get_shutter_input_2(zebra) == PC_GATE


class MyException(Exception):
    pass


def test_when_first_try_fails_then_bluesky_retry_tries_again(RE, done_status):
    mock_device = MagicMock(spec=Movable)

    @bluesky_retry
    def my_plan(value):
        yield from bps.abs_set(mock_device, value)

    mock_device.set.side_effect = [MyException(), done_status]

    RE(my_plan(10))

    assert mock_device.set.mock_calls == [call(10), call(10)]


def test_when_all_tries_fail_then_bluesky_retry_throws_error(RE, done_status):
    mock_device = MagicMock(spec=Movable)

    @bluesky_retry
    def my_plan(value):
        yield from bps.abs_set(mock_device, value)

    exception_2 = MyException()
    mock_device.set.side_effect = [MyException(), exception_2]

    with pytest.raises(MyException) as e:
        RE(my_plan(10))

    assert e.value == exception_2


async def test_configure_zebra_and_shutter_for_auto(
    RE, zebra: Zebra, zebra_shutter: ZebraShutter
):
    RE(configure_zebra_and_shutter_for_auto_shutter(zebra, zebra_shutter, IN4_TTL))
    assert await zebra_shutter.control_mode.get_value() == ZebraShutterControl.AUTO
    assert await _get_shutter_input_1(zebra) == SOFT_IN1
    assert await _get_shutter_input_2(zebra) == IN4_TTL
