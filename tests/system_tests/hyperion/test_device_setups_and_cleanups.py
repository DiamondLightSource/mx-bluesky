import pytest
from bluesky.run_engine import RunEngine
from dodal.beamlines.i03 import I03_ZEBRA_MAPPING
from dodal.devices.zebra.zebra import (
    I03Axes,
    Zebra,
)

from mx_bluesky.hyperion.device_setup_plans.setup_zebra import (
    setup_zebra_for_gridscan,
    setup_zebra_for_rotation,
    tidy_up_zebra_after_gridscan,
)


@pytest.fixture
async def connected_zebra():
    RunEngine()
    zebra = Zebra(name="zebra", prefix="BL03S-EA-ZEBRA-01:", mapping=I03_ZEBRA_MAPPING)
    await zebra.connect()
    return zebra


@pytest.mark.s03
async def test_zebra_set_up_for_gridscan(RE, connected_zebra: Zebra):
    RE(setup_zebra_for_gridscan(connected_zebra, wait=True))
    assert (
        connected_zebra.mapping.outputs.TTL_DETECTOR
        and connected_zebra.mapping.outputs.TTL_SHUTTER
    )
    assert (
        await connected_zebra.output.out_pvs[
            connected_zebra.mapping.outputs.TTL_DETECTOR
        ].get_value()
        == connected_zebra.mapping.sources.IN3_TTL
    )
    assert (
        await connected_zebra.output.out_pvs[
            connected_zebra.mapping.outputs.TTL_SHUTTER
        ].get_value()
        == connected_zebra.mapping.sources.IN4_TTL
    )


@pytest.mark.s03
async def test_zebra_set_up_for_rotation(RE, connected_zebra: Zebra):
    RE(setup_zebra_for_rotation(connected_zebra, wait=True))
    assert await connected_zebra.pc.gate_trigger.get_value() == I03Axes.OMEGA.value
    assert await connected_zebra.pc.gate_width.get_value() == pytest.approx(360, 0.01)


@pytest.mark.s03
async def test_zebra_cleanup(RE, connected_zebra: Zebra):
    assert (
        connected_zebra.mapping.outputs.TTL_DETECTOR
        and connected_zebra.mapping.outputs.TTL_SHUTTER
    )

    RE(tidy_up_zebra_after_gridscan(connected_zebra, wait=True))
    assert (
        await connected_zebra.output.out_pvs[
            connected_zebra.mapping.outputs.TTL_DETECTOR
        ].get_value()
        == connected_zebra.mapping.sources.PC_PULSE
    )
    assert (
        await connected_zebra.output.out_pvs[
            connected_zebra.mapping.outputs.TTL_SHUTTER
        ].get_value()
        == connected_zebra.mapping.sources.OR1
    )
