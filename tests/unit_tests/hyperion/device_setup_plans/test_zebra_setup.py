import pytest
from dodal.devices.zebra.zebra import (
    I03Axes,
    Zebra,
)
from dodal.devices.zebra.zebra_controlled_shutter import (
    ZebraShutter,
    ZebraShutterControl,
)

from mx_bluesky.hyperion.device_setup_plans.setup_zebra import (
    configure_zebra_and_shutter_for_auto_shutter,
    setup_zebra_for_gridscan,
    setup_zebra_for_panda_flyscan,
    setup_zebra_for_rotation,
    tidy_up_zebra_after_gridscan,
)


async def _get_shutter_input_2(zebra: Zebra):
    return (
        await zebra.logic_gates.and_gates[zebra.mapping.AND_GATE_FOR_AUTO_SHUTTER]
        .sources[2]
        .get_value()
    )


async def _get_shutter_input_1(zebra: Zebra):
    return (
        await zebra.logic_gates.and_gates[zebra.mapping.AND_GATE_FOR_AUTO_SHUTTER]
        .sources[1]
        .get_value()
    )


async def test_zebra_set_up_for_panda_gridscan(
    RE, zebra: Zebra, zebra_shutter: ZebraShutter
):
    RE(setup_zebra_for_panda_flyscan(zebra, zebra_shutter, wait=True))
    assert (
        await zebra.output.out_pvs[zebra.mapping.outputs.TTL_DETECTOR].get_value()
        == zebra.mapping.sources.IN1_TTL
    )
    assert (
        await zebra.output.out_pvs[zebra.mapping.outputs.TTL_PANDA].get_value()
        == zebra.mapping.sources.IN3_TTL
    )
    assert await zebra_shutter.control_mode.get_value() == ZebraShutterControl.AUTO
    assert await _get_shutter_input_2(zebra) == zebra.mapping.sources.IN4_TTL
    assert await _get_shutter_input_1(zebra) == zebra.mapping.sources.SOFT_IN1


async def test_zebra_set_up_for_gridscan(RE, zebra: Zebra, zebra_shutter: ZebraShutter):
    RE(setup_zebra_for_gridscan(zebra, zebra_shutter, wait=True))
    assert (
        await zebra.output.out_pvs[zebra.mapping.outputs.TTL_DETECTOR].get_value()
        == zebra.mapping.sources.IN3_TTL
    )
    assert await _get_shutter_input_2(zebra) == zebra.mapping.sources.IN4_TTL
    assert await zebra_shutter.control_mode.get_value() == ZebraShutterControl.AUTO
    assert await _get_shutter_input_1(zebra) == zebra.mapping.sources.SOFT_IN1


async def test_zebra_set_up_for_rotation(RE, zebra: Zebra, zebra_shutter: ZebraShutter):
    RE(setup_zebra_for_rotation(zebra, zebra_shutter, wait=True))
    assert await zebra.pc.gate_trigger.get_value() == I03Axes.OMEGA.value
    assert await zebra.pc.gate_width.get_value() == pytest.approx(360, 0.01)
    assert await zebra_shutter.control_mode.get_value() == ZebraShutterControl.AUTO
    assert await _get_shutter_input_1(zebra) == zebra.mapping.sources.SOFT_IN1


async def test_zebra_cleanup(RE, zebra: Zebra, zebra_shutter: ZebraShutter):
    RE(tidy_up_zebra_after_gridscan(zebra, zebra_shutter, wait=True))
    assert (
        await zebra.output.out_pvs[zebra.mapping.outputs.TTL_DETECTOR].get_value()
        == zebra.mapping.sources.PC_PULSE
    )
    assert await _get_shutter_input_2(zebra) == zebra.mapping.sources.PC_GATE


class MyException(Exception):
    pass


async def test_configure_zebra_and_shutter_for_auto(
    RE, zebra: Zebra, zebra_shutter: ZebraShutter
):
    RE(
        configure_zebra_and_shutter_for_auto_shutter(
            zebra, zebra_shutter, zebra.mapping.sources.IN4_TTL
        )
    )
    assert await zebra_shutter.control_mode.get_value() == ZebraShutterControl.AUTO
    assert await _get_shutter_input_1(zebra) == zebra.mapping.sources.SOFT_IN1
    assert await _get_shutter_input_2(zebra) == zebra.mapping.sources.IN4_TTL
