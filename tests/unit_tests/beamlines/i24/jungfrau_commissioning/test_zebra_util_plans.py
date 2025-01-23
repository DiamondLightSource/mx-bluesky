from unittest.mock import patch

import pytest
from dodal.devices.zebra.zebra import I24Axes, TrigSource, Zebra

from mx_bluesky.beamlines.i24.jungfrau_commissioning.plans.zebra_plans import (
    setup_zebra_for_rotation,
)


@patch("bluesky.plan_stubs.wait")
async def test_zebra_set_up_for_rotation(bps_wait, RE, zebra: Zebra):
    RE(setup_zebra_for_rotation(zebra, wait=True))
    assert (await zebra.pc.gate_trigger.get_value()) == I24Axes.OMEGA.value
    assert (await zebra.pc.gate_source.get_value()) == TrigSource.POSITION
    assert (await zebra.pc.pulse_source.get_value()) == TrigSource.TIME
    assert (await zebra.pc.gate_width.get_value()) == pytest.approx(370, abs=0.01)
    with pytest.raises(ValueError):
        RE(setup_zebra_for_rotation(zebra, direction=25))  # type: ignore
