import dataclasses
from unittest.mock import MagicMock, patch

import pytest
from dodal.devices.zebra.zebra import I24Axes, RotationDirection, Zebra
from dodal.devices.zebra.zebra_controlled_shutter import (
    ZebraShutter,
    ZebraShutterControl,
)

from mx_bluesky.common.device_setup_plans.setup_zebra_and_shutter import (
    configure_zebra_and_shutter_for_auto_shutter,
    setup_zebra_for_gridscan,
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


async def test_zebra_cleanup(RE, zebra: Zebra, zebra_shutter: ZebraShutter):
    RE(tidy_up_zebra_after_gridscan(zebra, zebra_shutter, wait=True))
    assert (
        await zebra.output.out_pvs[zebra.mapping.outputs.TTL_DETECTOR].get_value()
        == zebra.mapping.sources.PC_PULSE
    )
    assert await _get_shutter_input_2(zebra) == zebra.mapping.sources.PC_GATE


async def test_zebra_set_up_for_gridscan(RE, zebra: Zebra, zebra_shutter: ZebraShutter):
    @dataclasses.dataclass
    class Composite:
        zebra: Zebra
        sample_shutter: ZebraShutter

    composite = Composite(zebra, zebra_shutter)
    RE(setup_zebra_for_gridscan(composite, wait=True))
    assert (
        await zebra.output.out_pvs[zebra.mapping.outputs.TTL_DETECTOR].get_value()
        == zebra.mapping.sources.IN3_TTL
    )
    assert await _get_shutter_input_2(zebra) == zebra.mapping.sources.IN4_TTL
    assert await zebra_shutter.control_mode.get_value() == ZebraShutterControl.AUTO
    assert await _get_shutter_input_1(zebra) == zebra.mapping.sources.SOFT_IN1


@patch(
    "mx-bluesky.common.device_setup_plans.setup_zebra_for_rotation.configure_zebra_and_shutter_for_auto_shutter"
)
async def test_zebra_set_up_for_rotation(
    mock_setup_zebra_and_shutter: MagicMock,
    RE,
    zebra: Zebra,
    zebra_shutter: ZebraShutter,
):
    axis = I24Axes.OMEGA
    start_angle = 90
    scan_width = 180
    shutter_opening_deg = 1
    shutter_opening_s: float = 0.08
    direction = RotationDirection.NEGATIVE
    ttl_input_for_detector_to_use = 3
    zebra_output_to_disconnect = zebra.output.out_pvs[
        zebra.mapping.outputs.TTL_XSPRESS3
    ]

    RE(
        setup_zebra_for_rotation(
            zebra,
            zebra_shutter,
            axis,
            start_angle,
            scan_width,
            shutter_opening_deg,
            shutter_opening_s,
            direction,
            "group",
            True,
            ttl_input_for_detector_to_use,
            zebra_output_to_disconnect,
        )
    )
    assert await zebra.pc.gate_trigger.get_value() == axis
    assert await zebra.pc.gate_width.get_value() == pytest.approx(
        scan_width + shutter_opening_deg, 0.01
    )
    assert await zebra_shutter.control_mode.get_value() == ZebraShutterControl.AUTO
    assert await _get_shutter_input_1(zebra) == zebra.mapping.sources.SOFT_IN1
    assert await zebra.pc.dir.get_value() == direction
    assert await zebra.pc.gate_start.get_value() == start_angle
    assert zebra.pc.pulse_start.get_value() == shutter_opening_s
    mock_setup_zebra_and_shutter.assert_called_once()
    assert (
        zebra.output.out_pvs[ttl_input_for_detector_to_use].get_value()
        == zebra.mapping.sources.PC_PULSE
    )

    # test or remove the disconnect pulse 1?
