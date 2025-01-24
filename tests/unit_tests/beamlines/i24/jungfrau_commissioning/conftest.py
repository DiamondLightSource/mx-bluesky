import threading
import time
from collections.abc import Callable

import pytest
from dodal.beamlines import i24
from dodal.devices.attenuator.attenuator import EnumFilterAttenuator
from dodal.devices.i24.beam_params import ReadOnlyEnergyAndAttenuator
from dodal.devices.i24.jungfrau import JungFrau1M
from dodal.devices.i24.vgonio import VerticalGoniometer
from ophyd.status import Status
from ophyd_async.epics.motor import Motor
from ophyd_async.testing import callback_on_mock_put, set_mock_value

from mx_bluesky.beamlines.i24.jungfrau_commissioning.plans.rotation_scan_plans import (
    JfDevices,
)
from mx_bluesky.beamlines.i24.jungfrau_commissioning.utils.params import (
    RotationScanParameters,
)


@pytest.fixture
def params():
    return RotationScanParameters.from_file(
        "tests/unit_tests/beamlines/i24/jungfrau_commissioning/test_data/example_params.json"
    )


@pytest.fixture
def completed_status():
    result = Status()
    result.set_finished()
    return result


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
def fake_vgonio(RE):
    gon: VerticalGoniometer = i24.vgonio(fake_with_ophyd_sim=True)

    with (
        patch_motor(gon.x),
        patch_motor(gon.yh),
        patch_motor(gon.z),
        patch_motor(gon.omega),
    ):
        yield gon
    # def set_omega_side_effect(val):
    #     gon.omega.user_readback.sim_put(val)  # type: ignore
    #     return completed_status

    # gon.omega.set = MagicMock(side_effect=set_omega_side_effect)

    # gon.x.user_setpoint._use_limits = False
    # gon.yh.user_setpoint._use_limits = False
    # gon.z.user_setpoint._use_limits = False
    # gon.omega.user_setpoint._use_limits = False
    # return gon


@pytest.fixture
def fake_jungfrau(RE) -> JungFrau1M:
    JF: JungFrau1M = i24.jungfrau(fake_with_ophyd_sim=True)

    def set_acquire_side_effect(_, wait):
        set_mock_value(JF.acquire_rbv, 1)
        set_mock_value(JF.writing_rbv, 1)

        def go_low():
            time.sleep(1)
            set_mock_value(JF.acquire_rbv, 0)
            time.sleep(0.5)
            set_mock_value(JF.writing_rbv, 0)

        threading.Thread(target=go_low, daemon=True).start()
        # return completed_status

    callback_on_mock_put(JF.acquire_start, set_acquire_side_effect)

    return JF


@pytest.fixture
def fake_beam_params(RE) -> ReadOnlyEnergyAndAttenuator:
    BP: ReadOnlyEnergyAndAttenuator = i24.beam_params(fake_with_ophyd_sim=True)
    set_mock_value(BP.transmission, 0.1)
    set_mock_value(BP.energy, 20000)
    set_mock_value(BP.wavelength, 0.65)
    set_mock_value(BP.intensity, 9999999)
    return BP


@pytest.fixture
def attenuator(RE) -> EnumFilterAttenuator:
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
def fake_create_devices_function(fake_devices) -> Callable[..., JfDevices]:
    return lambda: fake_devices
