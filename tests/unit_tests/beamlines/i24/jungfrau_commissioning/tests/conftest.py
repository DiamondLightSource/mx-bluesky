import time
from collections.abc import Callable
from unittest.mock import MagicMock

import pytest
from dodal.devices.i24.i24_vgonio import VGonio
from ophyd.device import Device
from ophyd.status import Status

from mx_bluesky.beamlines.i24.jungfrau_commissioning.plans.rotation_scan_plans import (
    JfDevices,
)
from mx_bluesky.beamlines.i24.jungfrau_commissioning.utils import i24
from mx_bluesky.beamlines.i24.jungfrau_commissioning.utils.jf_commissioning_devices import (
    JungfrauM1,
    ReadOnlyEnergyAndAttenuator,
    SetAttenuator,
)


@pytest.fixture
def completed_status():
    result = Status()
    result.set_finished()
    return result


@pytest.fixture
def fake_vgonio(completed_status) -> VGonio:
    gon: VGonio = i24.vgonio(fake_with_ophyd_sim=True)

    def set_omega_side_effect(val):
        gon.omega.user_readback.sim_put(val)  # type: ignore
        return completed_status

    gon.omega.set = MagicMock(side_effect=set_omega_side_effect)

    gon.x.user_setpoint._use_limits = False
    gon.yh.user_setpoint._use_limits = False
    gon.z.user_setpoint._use_limits = False
    gon.omega.user_setpoint._use_limits = False
    return gon


@pytest.fixture
def fake_jungfrau() -> JungfrauM1:
    JF: JungfrauM1 = i24.jungfrau(fake_with_ophyd_sim=True)

    def set_acquire_side_effect(val):
        JF.acquire_rbv.sim_put(1)  # type: ignore
        time.sleep(1)
        JF.acquire_rbv.sim_put(0)  # type: ignore
        return completed_status

    JF.acquire_start.set = MagicMock(side_effect=set_acquire_side_effect)

    return JF


@pytest.fixture
def fake_beam_params() -> ReadOnlyEnergyAndAttenuator:
    BP: ReadOnlyEnergyAndAttenuator = i24.beam_params(fake_with_ophyd_sim=True)
    BP.transmission.sim_put(0.1)  # type: ignore
    BP.energy.sim_put(20000)  # type: ignore
    BP.wavelength.sim_put(0.65)  # type: ignore
    BP.intensity.sim_put(9999999)  # type: ignore
    return BP


@pytest.fixture
def attenuator() -> SetAttenuator:
    return i24.attenuator(fake_with_ophyd_sim=True)


@pytest.fixture
def fake_devices(
    fake_vgonio, fake_jungfrau, zebra, fake_beam_params, attenuator
) -> JfDevices:
    return {
        "jungfrau": fake_jungfrau,
        "gonio": fake_vgonio,
        "zebra": zebra,
        "beam_params": fake_beam_params,
        "attenuator": attenuator,
    }


@pytest.fixture
def fake_create_devices_function(fake_devices) -> Callable[..., dict[str, Device]]:
    return lambda: fake_devices
