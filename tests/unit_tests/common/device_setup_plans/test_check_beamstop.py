import pytest
from bluesky.run_engine import RunEngine
from dodal.devices.mx_phase1.beamstop import Beamstop
from ophyd_async.testing import set_mock_value

from mx_bluesky.common.device_setup_plans.check_beamstop import (
    BeamstopException,
    check_beamstop,
)


def test_beamstop_check_passes_when_in_beam(beamstop_i03: Beamstop, RE: RunEngine):
    set_mock_value(beamstop_i03.x_mm.user_readback, 1.52)
    set_mock_value(beamstop_i03.y_mm.user_readback, 44.78)
    set_mock_value(beamstop_i03.z_mm.user_readback, 30.0)
    RE(check_beamstop(beamstop_i03))


def test_beamstop_check_fails_when_not_in_beam(beamstop_i03: Beamstop, RE: RunEngine):
    set_mock_value(beamstop_i03.x_mm.user_readback, 0)
    set_mock_value(beamstop_i03.y_mm.user_readback, 0)
    set_mock_value(beamstop_i03.z_mm.user_readback, 0)
    with pytest.raises(BeamstopException, match="Beamstop is not DATA_COLLECTION"):
        RE(check_beamstop(beamstop_i03))
