from __future__ import annotations

from itertools import dropwhile, takewhile
from typing import Any
from unittest.mock import ANY, MagicMock, Mock, call, patch

import pytest
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from dodal.devices.aperturescatterguard import ApertureScatterguard, ApertureValue
from dodal.devices.backlight import BacklightPosition
from dodal.devices.detector.detector_motion import ShutterState
from dodal.devices.i03 import BeamstopPositions
from dodal.devices.oav.oav_parameters import OAVParameters
from dodal.devices.smargon import Smargon
from dodal.devices.synchrotron import SynchrotronMode
from dodal.devices.xbpm_feedback import Pause
from dodal.devices.zebra.zebra import RotationDirection, Zebra
from dodal.devices.zebra.zebra_controlled_shutter import ZebraShutterControl
from ophyd_async.testing import get_mock_put, set_mock_value

from mx_bluesky.common.device_setup_plans.check_beamstop import BeamstopException
from mx_bluesky.common.external_interaction.callbacks.common.zocalo_callback import (
    ZocaloCallback,
)
from mx_bluesky.common.external_interaction.ispyb.ispyb_store import IspybIds
from mx_bluesky.common.parameters.constants import DocDescriptorNames
from mx_bluesky.hyperion.experiment_plans.oav_snapshot_plan import (
    OAV_SNAPSHOT_GROUP,
)
from mx_bluesky.hyperion.experiment_plans.rotation_scan_plan import (
    RotationMotionProfile,
    RotationScanComposite,
    calculate_motion_profile,
    multi_rotation_scan,
    rotation_scan_plan,
)
from mx_bluesky.hyperion.external_interaction.callbacks.rotation.ispyb_callback import (
    RotationISPyBCallback,
)
from mx_bluesky.hyperion.parameters.constants import CONST
from mx_bluesky.hyperion.parameters.rotation import MultiRotationScan, RotationScan

from .conftest import fake_read

TEST_OFFSET = 1
TEST_SHUTTER_OPENING_DEGREES = 2.5


def do_rotation_main_plan_for_tests(
    run_eng: RunEngine,
    expt_params: RotationScan,
    devices: RotationScanComposite,
    motion_values: RotationMotionProfile,
):
    with patch(
        "bluesky.preprocessors.__read_and_stash_a_motor",
        fake_read,
    ):
        run_eng(
            rotation_scan_plan(devices, expt_params, motion_values),
        )


@pytest.fixture
def run_full_rotation_plan(
    RE: RunEngine,
    test_rotation_params: MultiRotationScan,
    fake_create_rotation_devices: RotationScanComposite,
    oav_parameters_for_rotation: OAVParameters,
) -> RotationScanComposite:
    with patch(
        "bluesky.preprocessors.__read_and_stash_a_motor",
        fake_read,
    ):
        RE(
            multi_rotation_scan(
                fake_create_rotation_devices,
                test_rotation_params,
                oav_parameters_for_rotation,
            ),
        )
        return fake_create_rotation_devices


@pytest.fixture
def motion_values(test_rotation_params: MultiRotationScan):
    params = next(test_rotation_params.single_rotation_scans)
    return calculate_motion_profile(
        params,
        0.005,  # time for acceleration
        222,
    )


def setup_and_run_rotation_plan_for_tests(
    RE: RunEngine,
    test_params: RotationScan,
    fake_create_rotation_devices: RotationScanComposite,
    motion_values,
):
    with patch("bluesky.plan_stubs.wait", autospec=True):
        do_rotation_main_plan_for_tests(
            RE, test_params, fake_create_rotation_devices, motion_values
        )

    return {
        "RE_with_subs": RE,
        "test_rotation_params": test_params,
        "smargon": fake_create_rotation_devices.smargon,
        "zebra": fake_create_rotation_devices.zebra,
    }


@pytest.fixture
def setup_and_run_rotation_plan_for_tests_standard(
    RE: RunEngine,
    test_rotation_params: MultiRotationScan,
    fake_create_rotation_devices: RotationScanComposite,
    motion_values: RotationMotionProfile,
):
    params = next(test_rotation_params.single_rotation_scans)
    return setup_and_run_rotation_plan_for_tests(
        RE, params, fake_create_rotation_devices, motion_values
    )


@pytest.fixture
def setup_and_run_rotation_plan_for_tests_nomove(
    RE: RunEngine,
    test_rotation_params_nomove: MultiRotationScan,
    fake_create_rotation_devices: RotationScanComposite,
    motion_values: RotationMotionProfile,
):
    rotation_params = next(test_rotation_params_nomove.single_rotation_scans)
    return setup_and_run_rotation_plan_for_tests(
        RE, rotation_params, fake_create_rotation_devices, motion_values
    )


def test_rotation_scan_calculations(test_rotation_params: MultiRotationScan):
    params = next(test_rotation_params.single_rotation_scans)
    params.features.omega_flip = False
    params.exposure_time_s = 0.2
    params.omega_start_deg = 10

    motion_values = calculate_motion_profile(
        params,
        0.005,  # time for acceleration
        224,
    )

    assert motion_values.direction == "Negative"
    assert motion_values.start_scan_deg == 10

    assert motion_values.speed_for_rotation_deg_s == 0.5  # 0.1 deg per 0.2 sec
    assert motion_values.shutter_time_s == 0.6
    assert motion_values.shutter_opening_deg == 0.3  # distance moved in 0.6 s

    # 1.5 * distance moved in time for accel (fudge)
    assert motion_values.acceleration_offset_deg == 0.00375
    assert motion_values.start_motion_deg == 10.00375

    assert motion_values.total_exposure_s == 360
    assert motion_values.scan_width_deg == 180
    assert motion_values.distance_to_move_deg == -180.3075


@patch(
    "dodal.common.beamlines.beamline_utils.active_device_is_same_type",
    lambda a, b: True,
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.rotation_scan_plan.rotation_scan_plan",
    autospec=True,
)
def test_rotation_scan(
    plan: MagicMock,
    RE: RunEngine,
    test_rotation_params: MultiRotationScan,
    fake_create_rotation_devices: RotationScanComposite,
    oav_parameters_for_rotation: OAVParameters,
):
    composite = fake_create_rotation_devices
    RE(
        multi_rotation_scan(
            composite, test_rotation_params, oav_parameters_for_rotation
        )
    )
    composite.eiger.do_arm.set.assert_called()  # type: ignore
    composite.eiger.unstage.assert_called()  # type: ignore


def test_rotation_plan_runs(
    setup_and_run_rotation_plan_for_tests_standard: dict[str, Any],
) -> None:
    RE: RunEngine = setup_and_run_rotation_plan_for_tests_standard["RE_with_subs"]
    assert RE._exit_status == "success"


async def test_rotation_plan_zebra_settings(
    setup_and_run_rotation_plan_for_tests_standard: dict[str, Any],
) -> None:
    zebra: Zebra = setup_and_run_rotation_plan_for_tests_standard["zebra"]
    params: RotationScan = setup_and_run_rotation_plan_for_tests_standard[
        "test_rotation_params"
    ]

    assert await zebra.pc.gate_start.get_value() == params.omega_start_deg
    assert await zebra.pc.pulse_start.get_value() == params.shutter_opening_time_s


async def test_full_rotation_plan_smargon_settings(
    run_full_rotation_plan: RotationScanComposite,
    test_rotation_params: MultiRotationScan,
) -> None:
    smargon: Smargon = run_full_rotation_plan.smargon
    params: RotationScan = next(test_rotation_params.single_rotation_scans)

    test_max_velocity = await smargon.omega.max_velocity.get_value()

    omega_set: MagicMock = get_mock_put(smargon.omega.user_setpoint)
    omega_velocity_set: MagicMock = get_mock_put(smargon.omega.velocity)
    rotation_speed = params.rotation_increment_deg / params.exposure_time_s

    assert await smargon.phi.user_setpoint.get_value() == params.phi_start_deg
    assert await smargon.chi.user_setpoint.get_value() == params.chi_start_deg
    assert await smargon.x.user_setpoint.get_value() == params.x_start_um / 1000  # type: ignore
    assert await smargon.y.user_setpoint.get_value() == params.y_start_um / 1000  # type: ignore
    assert await smargon.z.user_setpoint.get_value() == params.z_start_um / 1000  # type: ignore
    assert (
        # 4 * snapshots, restore omega, 1 * rotation sweep
        omega_set.call_count == 4 + 1 + 1
    )
    # 1 to max vel in outer plan, 1 to max vel in setup_oav_snapshot_plan, 1 set before rotation, 1 restore in cleanup plan
    assert omega_velocity_set.call_count == 4
    assert omega_velocity_set.call_args_list == [
        call(test_max_velocity, wait=True),
        call(test_max_velocity, wait=True),
        call(rotation_speed, wait=True),
        call(test_max_velocity, wait=True),
    ]


async def test_rotation_plan_moves_aperture_correctly(
    run_full_rotation_plan: RotationScanComposite,
) -> None:
    aperture_scatterguard: ApertureScatterguard = (
        run_full_rotation_plan.aperture_scatterguard
    )
    assert (
        await aperture_scatterguard.selected_aperture.get_value() == ApertureValue.SMALL
    )


async def test_rotation_plan_smargon_doesnt_move_xyz_if_not_given_in_params(
    setup_and_run_rotation_plan_for_tests_nomove: dict[str, Any],
) -> None:
    smargon: Smargon = setup_and_run_rotation_plan_for_tests_nomove["smargon"]
    params: RotationScan = setup_and_run_rotation_plan_for_tests_nomove[
        "test_rotation_params"
    ]
    assert params.phi_start_deg is None
    assert params.chi_start_deg is None
    assert params.x_start_um is None
    assert params.y_start_um is None
    assert params.z_start_um is None
    for motor in [smargon.phi, smargon.chi, smargon.x, smargon.y, smargon.z]:
        get_mock_put(motor.user_setpoint).assert_not_called()  # type: ignore


@patch(
    "mx_bluesky.hyperion.experiment_plans.rotation_scan_plan._cleanup_plan",
    autospec=True,
)
@patch("bluesky.plan_stubs.wait", autospec=True)
def test_cleanup_happens(
    bps_wait: MagicMock,
    cleanup_plan: MagicMock,
    RE: RunEngine,
    test_rotation_params: MultiRotationScan,
    fake_create_rotation_devices: RotationScanComposite,
    motion_values: RotationMotionProfile,
    oav_parameters_for_rotation: OAVParameters,
):
    class MyTestException(Exception):
        pass

    failing_set = MagicMock(
        side_effect=MyTestException("Experiment fails because this is a test")
    )

    with patch.object(fake_create_rotation_devices.smargon.omega, "set", failing_set):
        # check main subplan part fails
        params = next(test_rotation_params.single_rotation_scans)
        with pytest.raises(MyTestException):
            RE(rotation_scan_plan(fake_create_rotation_devices, params, motion_values))
        cleanup_plan.assert_not_called()
        # check that failure is handled in composite plan
        with pytest.raises(MyTestException) as exc:
            RE(
                multi_rotation_scan(
                    fake_create_rotation_devices,
                    test_rotation_params,
                    oav_parameters_for_rotation,
                )
            )
        assert "Experiment fails because this is a test" in exc.value.args[0]
        cleanup_plan.assert_called_once()


def test_rotation_plan_reads_hardware(
    fake_create_rotation_devices: RotationScanComposite,
    test_rotation_params: MultiRotationScan,
    motion_values,
    sim_run_engine_for_rotation: RunEngineSimulator,
):
    _add_sim_handlers_for_normal_operation(
        fake_create_rotation_devices, sim_run_engine_for_rotation
    )
    params = next(test_rotation_params.single_rotation_scans)
    msgs = sim_run_engine_for_rotation.simulate_plan(
        rotation_scan_plan(fake_create_rotation_devices, params, motion_values)
    )

    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "create"
        and msg.kwargs["name"] == CONST.DESCRIPTORS.HARDWARE_READ_PRE,
    )
    msgs_in_event = list(takewhile(lambda msg: msg.command != "save", msgs))
    assert_message_and_return_remaining(
        msgs_in_event, lambda msg: msg.command == "read" and msg.obj.name == "smargon"
    )


@pytest.fixture
def rotation_scan_simulated_messages(
    sim_run_engine: RunEngineSimulator,
    fake_create_rotation_devices: RotationScanComposite,
    test_rotation_params: MultiRotationScan,
    oav_parameters_for_rotation: OAVParameters,
):
    _add_sim_handlers_for_normal_operation(fake_create_rotation_devices, sim_run_engine)

    return sim_run_engine.simulate_plan(
        multi_rotation_scan(
            fake_create_rotation_devices,
            test_rotation_params,
            oav_parameters_for_rotation,
        )
    )


def test_rotation_scan_initialises_detector_distance_shutter_and_tx_fraction(
    rotation_scan_simulated_messages,
    test_rotation_params: MultiRotationScan,
):
    msgs = assert_message_and_return_remaining(
        rotation_scan_simulated_messages,
        lambda msg: msg.command == "set"
        and msg.args[0] == test_rotation_params.detector_distance_mm
        and msg.obj.name == "detector_motion-z"
        and msg.kwargs["group"] == CONST.WAIT.ROTATION_READY_FOR_DC,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.args[0] == ShutterState.OPEN
        and msg.obj.name == "detector_motion-shutter"
        and msg.kwargs["group"] == CONST.WAIT.ROTATION_READY_FOR_DC,
    )
    assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "wait"
        and msg.kwargs["group"] == CONST.WAIT.ROTATION_READY_FOR_DC,
    )


def test_rotation_scan_triggers_xbpm_then_pauses_xbpm_and_sets_transmission(
    rotation_scan_simulated_messages,
    test_rotation_params: MultiRotationScan,
):
    msgs = assert_message_and_return_remaining(
        rotation_scan_simulated_messages,
        lambda msg: msg.command == "trigger" and msg.obj.name == "xbpm_feedback",
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "xbpm_feedback-pause_feedback"
        and msg.args[0] == Pause.PAUSE.value,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "attenuator"
        and msg.args[0] == test_rotation_params.transmission_frac,
    )


def test_rotation_scan_does_not_change_transmission_back_until_after_data_collected(
    rotation_scan_simulated_messages,
    test_rotation_params: MultiRotationScan,
):
    msgs = assert_message_and_return_remaining(
        rotation_scan_simulated_messages,
        lambda msg: msg.command == "unstage" and msg.obj.name == "eiger",
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "xbpm_feedback-pause_feedback"
        and msg.args[0] == Pause.RUN.value,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "attenuator"
        and msg.args[0] == 1.0,
    )


def test_rotation_scan_moves_gonio_to_start_before_snapshots(
    rotation_scan_simulated_messages,
):
    msgs = assert_message_and_return_remaining(
        rotation_scan_simulated_messages,
        lambda msg: msg.command == "wait"
        and msg.kwargs["group"] == CONST.WAIT.MOVE_GONIO_TO_START,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "wait"
        and msg.kwargs["group"] == CONST.WAIT.READY_FOR_OAV,
    )


def test_rotation_scan_moves_aperture_in_backlight_out_after_snapshots_before_rotation(
    rotation_scan_simulated_messages,
):
    msgs = assert_message_and_return_remaining(
        rotation_scan_simulated_messages,
        lambda msg: msg.command == "create"
        and msg.kwargs["name"] == DocDescriptorNames.OAV_ROTATION_SNAPSHOT_TRIGGERED,
    )
    msgs = assert_message_and_return_remaining(msgs, lambda msg: msg.command == "save")
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "aperture_scatterguard-selected_aperture"
        and msg.args[0] == ApertureValue.SMALL
        and msg.kwargs["group"] == CONST.WAIT.ROTATION_READY_FOR_DC,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "backlight"
        and msg.args[0] == BacklightPosition.OUT
        and msg.kwargs["group"] == CONST.WAIT.ROTATION_READY_FOR_DC,
    )
    assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "wait"
        and msg.kwargs["group"] == CONST.WAIT.ROTATION_READY_FOR_DC,
    )


def test_rotation_scan_resets_omega_waits_for_sample_env_complete_after_snapshots_before_hw_read(
    test_rotation_params: MultiRotationScan, rotation_scan_simulated_messages
):
    params = next(test_rotation_params.single_rotation_scans)
    msgs = assert_message_and_return_remaining(
        rotation_scan_simulated_messages,
        lambda msg: msg.command == "create"
        and msg.kwargs["name"] == DocDescriptorNames.OAV_ROTATION_SNAPSHOT_TRIGGERED,
    )
    msgs = assert_message_and_return_remaining(msgs, lambda msg: msg.command == "save")
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "smargon-omega"
        and msg.args[0] == params.omega_start_deg
        and msg.kwargs["group"] == CONST.WAIT.ROTATION_READY_FOR_DC,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "wait"
        and msg.kwargs["group"] == CONST.WAIT.ROTATION_READY_FOR_DC,
    )
    assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "create"
        and msg.kwargs["name"] == CONST.DESCRIPTORS.ZOCALO_HW_READ,
    )


def test_rotation_snapshot_setup_called_to_move_backlight_in_aperture_out_before_triggering(
    rotation_scan_simulated_messages,
):
    msgs = assert_message_and_return_remaining(
        rotation_scan_simulated_messages,
        lambda msg: msg.command == "set"
        and msg.obj.name == "backlight"
        and msg.args[0] == BacklightPosition.IN
        and msg.kwargs["group"] == CONST.WAIT.READY_FOR_OAV,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "aperture_scatterguard-selected_aperture"
        and msg.args[0] == ApertureValue.OUT_OF_BEAM
        and msg.kwargs["group"] == CONST.WAIT.READY_FOR_OAV,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "wait"
        and msg.kwargs["group"] == CONST.WAIT.READY_FOR_OAV,
    )
    msgs = assert_message_and_return_remaining(
        msgs, lambda msg: msg.command == "trigger" and msg.obj.name == "oav-snapshot"
    )


def test_rotation_scan_skips_init_backlight_aperture_and_snapshots_if_snapshot_params_specified(
    fake_create_rotation_devices: RotationScanComposite,
    sim_run_engine: RunEngineSimulator,
    test_rotation_params: MultiRotationScan,
    oav_parameters_for_rotation: OAVParameters,
):
    _add_sim_handlers_for_normal_operation(fake_create_rotation_devices, sim_run_engine)
    test_rotation_params.snapshot_omegas_deg = None

    msgs = sim_run_engine.simulate_plan(
        multi_rotation_scan(
            fake_create_rotation_devices,
            test_rotation_params,
            oav_parameters_for_rotation,
        )
    )
    assert not [
        msg for msg in msgs if msg.kwargs.get("group", None) == CONST.WAIT.READY_FOR_OAV
    ]
    assert not [
        msg for msg in msgs if msg.kwargs.get("group", None) == OAV_SNAPSHOT_GROUP
    ]
    assert (
        len(
            [
                msg
                for msg in msgs
                if msg.command == "set"
                and msg.obj.name == "smargon-omega"
                and msg.kwargs["group"] == CONST.WAIT.ROTATION_READY_FOR_DC
            ]
        )
        == 1
    )


def _add_sim_handlers_for_normal_operation(
    fake_create_rotation_devices, sim_run_engine: RunEngineSimulator
):
    sim_run_engine.add_handler(
        "read",
        lambda msg: {"values": {"value": SynchrotronMode.USER}},
        "synchrotron-synchrotron_mode",
    )
    sim_run_engine.add_handler(
        "read",
        lambda msg: {"values": {"value": -1}},
        "synchrotron-top_up_start_countdown",
    )
    sim_run_engine.add_handler(
        "read", lambda msg: {"smargon-omega": {"value": -1}}, "smargon-omega"
    )


def test_rotation_scan_turns_shutter_to_auto_with_pc_gate_then_back_to_manual(
    fake_create_rotation_devices: RotationScanComposite,
    sim_run_engine: RunEngineSimulator,
    test_rotation_params: MultiRotationScan,
    oav_parameters_for_rotation: OAVParameters,
):
    _add_sim_handlers_for_normal_operation(fake_create_rotation_devices, sim_run_engine)
    msgs = sim_run_engine.simulate_plan(
        multi_rotation_scan(
            fake_create_rotation_devices,
            test_rotation_params,
            oav_parameters_for_rotation,
        )
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "sample_shutter-control_mode"
        and msg.args[0] == ZebraShutterControl.AUTO,  # type:ignore
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "zebra-logic_gates-and_gates-2-sources-1"
        and msg.args[0] == fake_create_rotation_devices.zebra.mapping.sources.SOFT_IN1,  # type:ignore
    )

    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "zebra-logic_gates-and_gates-2-sources-2"
        and msg.args[0] == fake_create_rotation_devices.zebra.mapping.sources.PC_GATE,  # type:ignore
    )

    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "sample_shutter-control_mode"
        and msg.args[0] == ZebraShutterControl.MANUAL,  # type:ignore
    )


def test_rotation_scan_arms_detector_and_takes_snapshots_whilst_arming(
    rotation_scan_simulated_messages,
    test_rotation_params,
    fake_create_rotation_devices,
    oav_parameters_for_rotation,
):
    composite = fake_create_rotation_devices
    msgs = assert_message_and_return_remaining(
        rotation_scan_simulated_messages,
        lambda msg: (
            msg.command == "open_run"
            and "BeamDrawingCallback" in msg.kwargs.get("activate_callbacks", [])
        ),
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "eiger_do_arm"
        and msg.args[0] == 1
        and msg.kwargs["group"] == CONST.WAIT.ROTATION_READY_FOR_DC,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj is composite.oav.snapshot.directory
        and msg.args[0] == str(test_rotation_params.snapshot_directory),
    )
    for omega in test_rotation_params.snapshot_omegas_deg:
        msgs = assert_message_and_return_remaining(
            msgs,
            lambda msg: msg.command == "set"
            and msg.obj is composite.smargon.omega
            and msg.args[0] == omega,
        )
        msgs = assert_message_and_return_remaining(
            msgs,
            lambda msg: msg.command == "set"
            and msg.obj is composite.oav.snapshot.filename
            and f"_oav_snapshot_{omega:.0f}" in msg.args[0],
        )
        msgs = assert_message_and_return_remaining(
            msgs,
            lambda msg: msg.command == "trigger" and msg.obj.name == "oav-snapshot",
        )
        msgs = assert_message_and_return_remaining(
            msgs,
            lambda msg: msg.command == "create"
            and msg.kwargs["name"]
            == DocDescriptorNames.OAV_ROTATION_SNAPSHOT_TRIGGERED,
        )
        msgs = assert_message_and_return_remaining(
            msgs, lambda msg: msg.command == "read" and msg.obj is composite.oav
        )
        msgs = assert_message_and_return_remaining(
            msgs, lambda msg: msg.command == "save"
        )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "wait"
        and msg.kwargs["group"] == CONST.WAIT.ROTATION_READY_FOR_DC,
    )


@patch(
    "mx_bluesky.hyperion.external_interaction.callbacks.rotation.ispyb_callback.StoreInIspyb"
)
def test_rotation_scan_correctly_triggers_ispyb_callback(
    mock_store_in_ispyb,
    RE: RunEngine,
    test_rotation_params: MultiRotationScan,
    fake_create_rotation_devices: RotationScanComposite,
    oav_parameters_for_rotation: OAVParameters,
):
    mock_ispyb_callback = RotationISPyBCallback()
    RE.subscribe(mock_ispyb_callback)
    with (
        patch("bluesky.plan_stubs.wait", autospec=True),
        patch(
            "bluesky.preprocessors.__read_and_stash_a_motor",
            fake_read,
        ),
    ):
        RE(
            multi_rotation_scan(
                fake_create_rotation_devices,
                test_rotation_params,
                oav_parameters_for_rotation,
            ),
        )
    mock_store_in_ispyb.assert_called()


@patch(
    "mx_bluesky.common.external_interaction.callbacks.common.zocalo_callback.ZocaloTrigger"
)
@patch(
    "mx_bluesky.hyperion.external_interaction.callbacks.rotation.ispyb_callback.StoreInIspyb"
)
def test_rotation_scan_correctly_triggers_zocalo_callback(
    mock_store_in_ispyb,
    mock_zocalo_interactor,
    RE: RunEngine,
    test_rotation_params: MultiRotationScan,
    fake_create_rotation_devices: RotationScanComposite,
    oav_parameters_for_rotation: OAVParameters,
):
    mock_zocalo_callback = ZocaloCallback(CONST.PLAN.ROTATION_MAIN, "env")
    mock_ispyb_callback = RotationISPyBCallback(emit=mock_zocalo_callback)
    mock_store_in_ispyb.return_value.update_deposition.return_value = IspybIds(
        data_collection_ids=(0, 1)
    )
    RE.subscribe(mock_ispyb_callback)
    with (
        patch("bluesky.plan_stubs.wait", autospec=True),
        patch(
            "bluesky.preprocessors.__read_and_stash_a_motor",
            fake_read,
        ),
    ):
        RE(
            multi_rotation_scan(
                fake_create_rotation_devices,
                test_rotation_params,
                oav_parameters_for_rotation,
            ),
        )
    mock_zocalo_interactor.return_value.run_start.assert_called_once()


def test_rotation_scan_fails_with_exception_when_no_beamstop(
    sim_run_engine: RunEngineSimulator,
    fake_create_rotation_devices: RotationScanComposite,
    test_rotation_params: MultiRotationScan,
    oav_parameters_for_rotation: OAVParameters,
):
    sim_run_engine.add_read_handler_for(
        fake_create_rotation_devices.beamstop.selected_pos, BeamstopPositions.UNKNOWN
    )
    with pytest.raises(BeamstopException):
        sim_run_engine.simulate_plan(
            multi_rotation_scan(
                fake_create_rotation_devices,
                test_rotation_params,
                oav_parameters_for_rotation,
            )
        )


@pytest.mark.timeout(2)
@pytest.mark.parametrize(
    "omega_flip, rotation_direction, expected_start_angle, "
    "expected_start_angle_with_runup, expected_zebra_direction",
    [
        # see https://github.com/DiamondLightSource/mx-bluesky/issues/247
        # GDA behaviour is such that positive angles in the request result in
        # negative motor angles, but positive angles in the resulting nexus file
        # Should replicate GDA Output exactly
        [True, RotationDirection.POSITIVE, -30, -29.85, RotationDirection.NEGATIVE],
        # Should replicate GDA Output, except with /entry/data/transformation/omega
        # +1, 0, 0 instead of -1, 0, 0
        [False, RotationDirection.NEGATIVE, 30, 30.15, RotationDirection.NEGATIVE],
        [True, RotationDirection.NEGATIVE, -30, -30.15, RotationDirection.POSITIVE],
        [False, RotationDirection.POSITIVE, 30, 29.85, RotationDirection.POSITIVE],
    ],
)
@patch(
    "mx_bluesky.common.external_interaction.callbacks.common.zocalo_callback.ZocaloTrigger",
    MagicMock(),
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.rotation_scan_plan.setup_zebra_for_rotation"
)
def test_rotation_scan_plan_with_omega_flip_inverts_motor_movements_but_not_event_params(
    mock_setup_zebra_for_rotation: MagicMock,
    omega_flip: bool,
    rotation_direction: RotationDirection,
    expected_start_angle: float,
    expected_start_angle_with_runup: float,
    expected_zebra_direction: RotationDirection,
    test_rotation_params: MultiRotationScan,
    fake_create_rotation_devices: RotationScanComposite,
    oav_parameters_for_rotation: OAVParameters,
    RE: RunEngine,
):
    test_rotation_params.features.omega_flip = omega_flip
    for scan in test_rotation_params.rotation_scans:  # Should be 1 scan
        scan.rotation_direction = rotation_direction
        scan.omega_start_deg = 30
    mock_callback = Mock(spec=RotationISPyBCallback)
    RE.subscribe(mock_callback)
    omega_put = get_mock_put(fake_create_rotation_devices.smargon.omega.user_setpoint)
    set_mock_value(fake_create_rotation_devices.smargon.omega.acceleration_time, 0.1)
    with (
        patch("bluesky.plan_stubs.wait", autospec=True),
        patch(
            "bluesky.preprocessors.__read_and_stash_a_motor",
            fake_read,
        ),
    ):
        RE(
            multi_rotation_scan(
                fake_create_rotation_devices,
                test_rotation_params,
                oav_parameters_for_rotation,
            ),
        )

    assert omega_put.mock_calls[0:5] == [
        call(0, wait=True),
        call(90, wait=True),
        call(180, wait=True),
        call(270, wait=True),
        call(expected_start_angle_with_runup, wait=True),
    ]
    mock_setup_zebra_for_rotation.assert_called_once_with(
        fake_create_rotation_devices.zebra,
        fake_create_rotation_devices.sample_shutter,
        start_angle=expected_start_angle,
        scan_width=180,
        direction=expected_zebra_direction,
        shutter_opening_deg=ANY,
        shutter_opening_s=ANY,
        group="setup_zebra",
    )
    rotation_outer_start_event = next(
        dropwhile(
            lambda _: _.args[0] != "start"
            or _.args[1].get("subplan_name") != CONST.PLAN.ROTATION_OUTER,
            mock_callback.mock_calls,
        )
    )
    event_params = RotationScan.model_validate_json(
        rotation_outer_start_event.args[1]["mx_bluesky_parameters"]
    )
    # event params are not transformed
    assert event_params.rotation_increment_deg == 0.1
    assert event_params.features.omega_flip == omega_flip
    assert event_params.rotation_direction == rotation_direction
    assert event_params.scan_width_deg == 180
    assert event_params.omega_start_deg == 30


def test_rotation_scan_does_not_verify_undulator_gap_until_before_run(
    rotation_scan_simulated_messages,
    test_rotation_params: MultiRotationScan,
):
    msgs = rotation_scan_simulated_messages
    msgs = assert_message_and_return_remaining(
        msgs, lambda msg: msg.command == "set" and msg.obj.name == "undulator"
    )
    msgs = assert_message_and_return_remaining(
        msgs, lambda msg: msg.command == "open_run"
    )
