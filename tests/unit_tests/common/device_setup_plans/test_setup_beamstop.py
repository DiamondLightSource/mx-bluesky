from unittest.mock import MagicMock

from bluesky.run_engine import RunEngine
from dodal.devices.mx_phase1.beamstop import Beamstop
from ophyd_async.testing import set_mock_value

from mx_bluesky.common.device_setup_plans.setup_beamstop import (
    setup_beamstop_for_collection,
)


def test_setup_beamstop_does_nothing_when_beamstop_in_beam(
    beamstop_i03: Beamstop, RE: RunEngine
):
    beamstop_i03.x_mm.set = MagicMock()
    beamstop_i03.y_mm.set = MagicMock()
    beamstop_i03.z_mm.set = MagicMock()

    set_mock_value(beamstop_i03.x_mm.user_readback, 1.52)
    set_mock_value(beamstop_i03.y_mm.user_readback, 44.78)
    set_mock_value(beamstop_i03.z_mm.user_readback, 30.0)

    RE(setup_beamstop_for_collection(beamstop_i03))

    assert beamstop_i03.x_mm.set.call_count == 0
    assert beamstop_i03.y_mm.set.call_count == 0
    assert beamstop_i03.z_mm.set.call_count == 0


def test_setup_beamstop_moves_beamstop_into_beam_when_not_in_beam(
    beamstop_i03: Beamstop, RE: RunEngine
):
    beamstop_i03.x_mm.set = MagicMock()
    beamstop_i03.y_mm.set = MagicMock()
    beamstop_i03.z_mm.set = MagicMock()
    set_mock_value(beamstop_i03.x_mm.user_readback, 0)
    set_mock_value(beamstop_i03.y_mm.user_readback, 0)
    set_mock_value(beamstop_i03.z_mm.user_readback, 0)
    RE(setup_beamstop_for_collection(beamstop_i03))

    assert beamstop_i03.x_mm.set.call_count == 1
    assert beamstop_i03.x_mm.set.call_args[0][0] == 1.52

    assert beamstop_i03.y_mm.set.call_count == 1
    assert beamstop_i03.y_mm.set.call_args[0][0] == 44.78

    assert beamstop_i03.z_mm.set.call_count == 1
    assert beamstop_i03.z_mm.set.call_args[0][0] == 30.0
