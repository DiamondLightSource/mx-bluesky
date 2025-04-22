from unittest.mock import MagicMock, call

import pytest
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from dodal.devices.focusing_mirror import (
    FocusingMirrorWithStripes,
    MirrorStripe,
    MirrorVoltages,
)
from dodal.devices.i03.undulator_dcm import UndulatorDCM
from ophyd_async.testing import get_mock_put

from mx_bluesky.hyperion.device_setup_plans import dcm_pitch_roll_mirror_adjuster
from mx_bluesky.hyperion.device_setup_plans.dcm_pitch_roll_mirror_adjuster import (
    YAW_LAT_TIMEOUT_S,
    adjust_dcm_pitch_roll_vfm_from_lut,
    adjust_mirror_stripe,
)


def test_when_bare_mirror_stripe_selected_then_expected_voltages_set_and_waited(
    sim_run_engine: RunEngineSimulator,
    mirror_voltages: MirrorVoltages,
):
    messages = sim_run_engine.simulate_plan(
        dcm_pitch_roll_mirror_adjuster._apply_and_wait_for_voltages_to_settle(
            MirrorStripe.BARE, mirror_voltages
        )
    )

    for channel, expected_voltage in zip(
        mirror_voltages.horizontal_voltages.values(),
        [1, 107, 15, 139, 41, 165, 11, 6, 166, -65, 0, -38, 179, 128],
        strict=True,
    ):
        messages = assert_message_and_return_remaining(
            messages,
            lambda msg: msg.command == "set"
            and msg.obj == channel
            and msg.args[0] == expected_voltage,
        )
        messages = assert_message_and_return_remaining(
            messages, lambda msg: msg.command == "wait"
        )

    for channel, expected_voltage in zip(
        mirror_voltages.vertical_voltages.values(),
        [140, 100, 70, 30, 30, -65, 24, 15],
        strict=True,
    ):
        messages = assert_message_and_return_remaining(
            messages,
            lambda msg: msg.command == "set"
            and msg.obj == channel
            and msg.args[0] == expected_voltage,
        )
        messages = assert_message_and_return_remaining(
            messages, lambda msg: msg.command == "wait"
        )


@pytest.mark.parametrize(
    "energy_kev, expected_stripe, expected_lat, expected_yaw, first_voltage, last_voltage",
    [
        (6.999, MirrorStripe.BARE, 0.0, 6.2, 140, 15),
        (7.001, MirrorStripe.RHODIUM, 10.0, 0.0, 124, -46),
    ],
)
def test_adjust_mirror_stripe(
    RE: RunEngine,
    mirror_voltages: MirrorVoltages,
    vfm: FocusingMirrorWithStripes,
    energy_kev,
    expected_stripe,
    expected_lat,
    expected_yaw,
    first_voltage,
    last_voltage,
):
    parent = MagicMock()
    parent.attach_mock(get_mock_put(vfm.stripe), "stripe_set")
    parent.attach_mock(get_mock_put(vfm.apply_stripe), "apply_stripe")
    parent.attach_mock(get_mock_put(vfm.x_mm.user_setpoint), "lat_set")
    parent.attach_mock(get_mock_put(vfm.yaw_mrad.user_setpoint), "yaw_mrad")

    RE(adjust_mirror_stripe(energy_kev, vfm, mirror_voltages))

    expected_calls = [
        call.stripe_set(expected_stripe, wait=True),
        call.apply_stripe(None, wait=True),
        call.lat_set(expected_lat, wait=True),
        call.yaw_mrad(expected_yaw, wait=True),
    ]
    assert parent.method_calls == expected_calls
    mirror_voltages.vertical_voltages[0].set.assert_called_once_with(  # type: ignore
        first_voltage
    )
    mirror_voltages.vertical_voltages[7].set.assert_called_once_with(  # type: ignore
        last_voltage
    )


def test_adjust_dcm_pitch_roll_vfm_from_lut(
    undulator_dcm: UndulatorDCM,
    vfm: FocusingMirrorWithStripes,
    mirror_voltages: MirrorVoltages,
    sim_run_engine: RunEngineSimulator,
):
    sim_run_engine.add_handler_for_callback_subscribes()

    messages = sim_run_engine.simulate_plan(
        adjust_dcm_pitch_roll_vfm_from_lut(undulator_dcm, vfm, mirror_voltages, 7.5)
    )
    # target bragg angle 15.288352 deg
    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "set"
        and msg.obj.name == "dcm-xtal_1-pitch_in_mrad"
        and abs(msg.args[0] - -0.78229639) < 1e-5
        and msg.kwargs["group"] == "DCM_GROUP",
    )
    messages = assert_message_and_return_remaining(
        messages[1:],
        lambda msg: msg.command == "set"
        and msg.obj.name == "dcm-xtal_1-roll_in_mrad"
        and abs(msg.args[0] - -0.2799) < 1e-5
        and msg.kwargs["group"] == "DCM_GROUP",
    )
    messages = assert_message_and_return_remaining(
        messages[1:],
        lambda msg: msg.command == "set"
        and msg.obj.name == "vfm-stripe"
        and msg.args == (MirrorStripe.RHODIUM,),
    )
    messages = assert_message_and_return_remaining(
        messages[1:],
        lambda msg: msg.command == "wait",
    )
    messages = assert_message_and_return_remaining(
        messages[1:],
        lambda msg: msg.command == "trigger" and msg.obj.name == "vfm-apply_stripe",
    )
    messages = assert_message_and_return_remaining(
        messages[1:],
        lambda msg: msg.command == "set"
        and msg.obj is vfm.x_mm
        and msg.args == (10.0,)
        and msg.kwargs["timeout"] == YAW_LAT_TIMEOUT_S,
    )
    messages = assert_message_and_return_remaining(
        messages[1:], lambda msg: msg.command == "wait"
    )
    messages = assert_message_and_return_remaining(
        messages[1:],
        lambda msg: msg.command == "set"
        and msg.obj is vfm.yaw_mrad
        and msg.args == (0.0,)
        and msg.kwargs["timeout"] == YAW_LAT_TIMEOUT_S,
    )
    messages = assert_message_and_return_remaining(
        messages[1:], lambda msg: msg.command == "wait"
    )
    for channel, expected_voltage in enumerate(
        [11, 117, 25, 149, 51, 145, -9, -14, 146, -10, 55, 17, 144, 93]
    ):
        messages = assert_message_and_return_remaining(
            messages[1:],
            lambda msg: msg.command == "set"
            and msg.obj.name == f"mirror_voltages-horizontal_voltages-{channel}"
            and msg.args == (expected_voltage,),
        )
    for channel, expected_voltage in enumerate([124, 114, 34, 49, 19, -116, 4, -46]):
        messages = assert_message_and_return_remaining(
            messages[1:],
            lambda msg: msg.command == "set"
            and msg.obj.name == f"mirror_voltages-vertical_voltages-{channel}"
            and msg.args == (expected_voltage,),
        )
