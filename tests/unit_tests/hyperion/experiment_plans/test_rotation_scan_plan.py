from __future__ import annotations

import json
import shutil
from collections.abc import Callable, Sequence
from itertools import dropwhile, takewhile
from math import ceil
from typing import Any
from unittest.mock import ANY, MagicMock, Mock, call, patch

import h5py
import numpy as np
import pytest
from bluesky import Msg
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
from ophyd.status import Status
from ophyd_async.testing import get_mock_put, set_mock_value

from mx_bluesky.common.external_interaction.callbacks.common.zocalo_callback import (
    ZocaloCallback,
)
from mx_bluesky.common.external_interaction.ispyb.ispyb_store import (
    IspybIds,
    StoreInIspyb,
)
from mx_bluesky.common.external_interaction.nexus.nexus_utils import AxisDirection
from mx_bluesky.common.parameters.constants import DocDescriptorNames
from mx_bluesky.common.utils.exceptions import ISPyBDepositionNotMade
from mx_bluesky.hyperion.experiment_plans.oav_snapshot_plan import (
    OAV_SNAPSHOT_GROUP,
)
from mx_bluesky.hyperion.experiment_plans.rotation_scan_plan import (
    RotationMotionProfile,
    RotationScanComposite,
    calculate_motion_profile,
    rotation_scan,
    rotation_scan_plan,
)
from mx_bluesky.hyperion.external_interaction.callbacks.__main__ import (
    create_rotation_callbacks,
)
from mx_bluesky.hyperion.external_interaction.callbacks.rotation.ispyb_callback import (
    RotationISPyBCallback,
)
from mx_bluesky.hyperion.external_interaction.callbacks.rotation.nexus_callback import (
    RotationNexusFileCallback,
)
from mx_bluesky.hyperion.parameters.constants import CONST
from mx_bluesky.hyperion.parameters.rotation import MultiRotationScan, RotationScan

from ....conftest import (
    DocumentCapturer,
    extract_metafile,
    fake_read,
    mx_acquisition_from_conn,
    raw_params_from_file,
    remap_upsert_columns,
)

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
            rotation_scan(
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
    RE(rotation_scan(composite, test_rotation_params, oav_parameters_for_rotation))
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
                rotation_scan(
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
        rotation_scan(
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
        rotation_scan(
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
        rotation_scan(
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
            rotation_scan(
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
            rotation_scan(
                fake_create_rotation_devices,
                test_rotation_params,
                oav_parameters_for_rotation,
            ),
        )
    mock_zocalo_interactor.return_value.run_start.assert_called_once()


def test_rotation_scan_moves_beamstop_into_place(
    sim_run_engine: RunEngineSimulator,
    fake_create_rotation_devices: RotationScanComposite,
    test_rotation_params: MultiRotationScan,
    oav_parameters_for_rotation: OAVParameters,
):
    with patch(
        "mx_bluesky.hyperion.experiment_plans.rotation_scan_plan.rotation_scan_plan"
    ) as mock_rotation_scan_plan:
        mock_rotation_scan_plan.return_value = iter([Msg("rotation_scan_plan")])
        msgs = sim_run_engine.simulate_plan(
            rotation_scan(
                fake_create_rotation_devices,
                test_rotation_params,
                oav_parameters_for_rotation,
            )
        )
    msgs = assert_message_and_return_remaining(
        msgs,
        predicate=lambda msg: msg.command == "set"
        and msg.obj.name == "beamstop-selected_pos"
        and msg.args[0] == BeamstopPositions.DATA_COLLECTION,
    )
    msgs = assert_message_and_return_remaining(
        msgs, predicate=lambda msg: msg.command == "rotation_scan_plan"
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
            rotation_scan(
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


def test_multi_rotation_scan_params():
    raw_params = raw_params_from_file(
        "tests/test_data/parameter_json_files/good_test_multi_rotation_scan_parameters.json"
    )
    params = MultiRotationScan(**raw_params)
    omega_starts = [s["omega_start_deg"] for s in raw_params["rotation_scans"]]
    for i, scan in enumerate(params.single_rotation_scans):
        assert scan.omega_start_deg == omega_starts[i]
        assert scan.nexus_vds_start_img == params.scan_indices[i]
        assert params.scan_indices

    detector_params = params.detector_params
    # MX-bluesky 563 assumptions are made about DetectorParams which aren't true for this test file
    assert detector_params.num_images_per_trigger == 1800
    assert detector_params.num_triggers == 3
    assert detector_params.omega_start == 0


async def test_multi_rotation_plan_runs_multiple_plans_in_one_arm(
    fake_create_rotation_devices: RotationScanComposite,
    test_multi_rotation_params: MultiRotationScan,
    sim_run_engine_for_rotation: RunEngineSimulator,
    oav_parameters_for_rotation: OAVParameters,
):
    smargon = fake_create_rotation_devices.smargon
    omega = smargon.omega
    set_mock_value(
        fake_create_rotation_devices.synchrotron.synchrotron_mode, SynchrotronMode.USER
    )
    msgs = sim_run_engine_for_rotation.simulate_plan(
        rotation_scan(
            fake_create_rotation_devices,
            test_multi_rotation_params,
            oav_parameters_for_rotation,
        )
    )

    msgs = assert_message_and_return_remaining(
        msgs, lambda msg: msg.command == "set" and msg.obj.name == "eiger_do_arm"
    )[1:]

    msgs_within_arming = list(
        takewhile(
            lambda msg: msg.command != "unstage"
            and (not msg.obj or msg.obj.name != "eiger"),
            msgs,
        )
    )

    def _assert_set_seq_and_return_remaining(remaining, name_value_pairs):
        for name, value in name_value_pairs:
            try:
                remaining = assert_message_and_return_remaining(
                    remaining,
                    lambda msg: msg.command == "set"
                    and msg.obj.name == name
                    and msg.args == (value,),
                )
            except Exception as e:
                raise Exception(f"Failed to find {name} being set to {value}") from e
        return remaining

    for scan in test_multi_rotation_params.single_rotation_scans:
        motion_values = calculate_motion_profile(
            scan,
            (await omega.acceleration_time.get_value()),
            (await omega.max_velocity.get_value()),
        )
        # moving to the start position
        msgs_within_arming = _assert_set_seq_and_return_remaining(
            msgs_within_arming,
            [
                ("smargon-x", scan.x_start_um / 1000),  # type: ignore
                ("smargon-y", scan.y_start_um / 1000),  # type: ignore
                ("smargon-z", scan.z_start_um / 1000),  # type: ignore
                ("smargon-phi", scan.phi_start_deg),
                ("smargon-chi", scan.chi_start_deg),
            ],
        )
        # arming the zebra
        msgs_within_arming = assert_message_and_return_remaining(
            msgs_within_arming,
            lambda msg: msg.command == "set" and msg.obj.name == "zebra-pc-arm",
        )
        # the final rel_set of omega to trigger the scan
        assert_message_and_return_remaining(
            msgs_within_arming,
            lambda msg: msg.command == "set"
            and msg.obj.name == "smargon-omega"
            and msg.args
            == (
                (scan.scan_width_deg + motion_values.shutter_opening_deg)
                * motion_values.direction.multiplier,
            ),
        )


def _run_multi_rotation_plan(
    RE: RunEngine,
    params: MultiRotationScan,
    devices: RotationScanComposite,
    callbacks: Sequence[Callable[[str, dict[str, Any]], Any]],
    oav_params: OAVParameters,
):
    for cb in callbacks:
        RE.subscribe(cb)
    with patch("bluesky.preprocessors.__read_and_stash_a_motor", fake_read):
        RE(rotation_scan(devices, params, oav_params))


@patch(
    "mx_bluesky.hyperion.experiment_plans.rotation_scan_plan.check_topup_and_wait_if_necessary",
    autospec=True,
)
def test_full_multi_rotation_plan_docs_emitted(
    _,
    RE: RunEngine,
    test_multi_rotation_params: MultiRotationScan,
    fake_create_rotation_devices: RotationScanComposite,
    oav_parameters_for_rotation: OAVParameters,
):
    callback_sim = DocumentCapturer()
    _run_multi_rotation_plan(
        RE,
        test_multi_rotation_params,
        fake_create_rotation_devices,
        [callback_sim],
        oav_parameters_for_rotation,
    )
    docs = callback_sim.docs_received

    assert (
        outer_plan_start_doc := DocumentCapturer.assert_doc(
            docs, "start", matches_fields=({"plan_name": "rotation_scan"})
        )
    )
    outer_uid = outer_plan_start_doc[1]["uid"]
    inner_run_docs = DocumentCapturer.get_docs_until(
        docs,
        "stop",
        matches_fields=({"run_start": outer_uid, "exit_status": "success"}),
    )[1:-1]

    for scan in test_multi_rotation_params.single_rotation_scans:
        inner_run_docs = DocumentCapturer.get_docs_from(
            inner_run_docs,
            "start",
            matches_fields={"subplan_name": "rotation_scan_with_cleanup"},
        )
        scan_docs = DocumentCapturer.get_docs_until(
            inner_run_docs,
            "stop",
            matches_fields={"run_start": inner_run_docs[0][1]["uid"]},
        )
        params = RotationScan(**json.loads(scan_docs[0][1]["mx_bluesky_parameters"]))
        assert params == scan
        assert len(events := DocumentCapturer.get_matches(scan_docs, "event")) == 3
        DocumentCapturer.assert_events_and_data_in_order(
            events,
            [
                ["eiger_odin_file_writer_id"],
                ["undulator-current_gap", "synchrotron-synchrotron_mode", "smargon-x"],
                [
                    "attenuator-actual_transmission",
                    "flux-flux_reading",
                    "dcm-energy_in_kev",
                    "eiger_bit_depth",
                ],
            ],
        )
        inner_run_docs = DocumentCapturer.get_docs_from(
            inner_run_docs,
            "stop",
            matches_fields={"run_start": inner_run_docs[0][1]["uid"]},
        )


@patch(
    "mx_bluesky.hyperion.external_interaction.callbacks.rotation.nexus_callback.NexusWriter"
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.rotation_scan_plan.check_topup_and_wait_if_necessary",
    autospec=True,
)
def test_full_multi_rotation_plan_nexus_writer_called_correctly(
    _,
    mock_nexus_writer: MagicMock,
    RE: RunEngine,
    test_multi_rotation_params: MultiRotationScan,
    fake_create_rotation_devices: RotationScanComposite,
    oav_parameters_for_rotation: OAVParameters,
):
    callback = RotationNexusFileCallback()
    _run_multi_rotation_plan(
        RE,
        test_multi_rotation_params,
        fake_create_rotation_devices,
        [callback],
        oav_parameters_for_rotation,
    )
    nexus_writer_calls = mock_nexus_writer.call_args_list
    first_run_number = test_multi_rotation_params.detector_params.run_number
    for writer_call, rotation_params in zip(
        nexus_writer_calls,
        test_multi_rotation_params.single_rotation_scans,
        strict=False,
    ):
        callback_params = writer_call.args[0]
        assert callback_params == rotation_params
        assert writer_call.kwargs == {
            "omega_start_deg": rotation_params.omega_start_deg,
            "chi_start_deg": rotation_params.chi_start_deg,
            "phi_start_deg": rotation_params.phi_start_deg,
            "vds_start_index": rotation_params.nexus_vds_start_img,
            "full_num_of_images": test_multi_rotation_params.num_images,
            "meta_data_run_number": first_run_number,
            "axis_direction": AxisDirection.NEGATIVE
            if rotation_params.features.omega_flip
            else AxisDirection.POSITIVE,
        }


@pytest.mark.timeout(2)
@patch(
    "mx_bluesky.hyperion.experiment_plans.rotation_scan_plan.check_topup_and_wait_if_necessary",
    autospec=True,
)
def test_full_multi_rotation_plan_nexus_files_written_correctly(
    _,
    RE: RunEngine,
    feature_flags_update_with_omega_flip: MagicMock,
    test_multi_rotation_params: MultiRotationScan,
    fake_create_rotation_devices: RotationScanComposite,
    oav_parameters_for_rotation: OAVParameters,
    tmpdir,
):
    multi_params = test_multi_rotation_params
    prefix = "multi_rotation_test"
    test_data_dir = "tests/test_data/nexus_files/"
    meta_file = f"{test_data_dir}rotation/ins_8_5_meta.h5.gz"
    fake_datafile = f"{test_data_dir}fake_data.h5"
    multi_params.file_name = prefix
    multi_params.storage_directory = f"{tmpdir}"
    meta_data_run_number = multi_params.detector_params.run_number

    data_filename_prefix = f"{prefix}_{meta_data_run_number}_"
    meta_filename = f"{prefix}_{meta_data_run_number}_meta.h5"

    callback = RotationNexusFileCallback()
    _run_multi_rotation_plan(
        RE,
        multi_params,
        fake_create_rotation_devices,
        [callback],
        oav_parameters_for_rotation,
    )

    def _expected_dset_number(image_number: int):
        # image numbers 0-999 are in dset 1, etc.
        return int(ceil((image_number + 1) / 1000))

    num_datasets = range(
        1, _expected_dset_number(multi_params.num_images - 1)
    )  # the index of the last image is num_images - 1

    for i in num_datasets:
        shutil.copy(
            fake_datafile,
            f"{tmpdir}/{data_filename_prefix}{i:06d}.h5",
        )
    extract_metafile(
        meta_file,
        f"{tmpdir}/{meta_filename}",
    )
    for i, scan in enumerate(multi_params.single_rotation_scans):
        with h5py.File(f"{tmpdir}/{prefix}_{i + 1}.nxs", "r") as written_nexus_file:
            # check links go to the right file:
            detector_specific = written_nexus_file[
                "entry/instrument/detector/detectorSpecific"
            ]
            for field in ["software_version"]:
                link = detector_specific.get(field, getlink=True)  # type: ignore
                assert link.filename == meta_filename  # type: ignore
            data_group = written_nexus_file["entry/data"]
            for field in [f"data_{n:06d}" for n in num_datasets]:
                link = data_group.get(field, getlink=True)  # type: ignore
                assert link.filename.startswith(data_filename_prefix)  # type: ignore

            # check dataset starts and stops are correct:
            assert isinstance(dataset := data_group["data"], h5py.Dataset)  # type: ignore
            assert dataset.is_virtual
            assert dataset[scan.num_images - 1, 0, 0] == 0
            with pytest.raises(IndexError):
                assert dataset[scan.num_images, 0, 0] == 0
            dataset_sources = dataset.virtual_sources()
            expected_dset_start = _expected_dset_number(multi_params.scan_indices[i])
            expected_dset_end = _expected_dset_number(multi_params.scan_indices[i + 1])
            dset_start_name = dataset_sources[0].dset_name
            dset_end_name = dataset_sources[-1].dset_name
            assert dset_start_name.endswith(f"data_{expected_dset_start:06d}")
            assert dset_end_name.endswith(f"data_{expected_dset_end:06d}")

            # check scan values are correct for each file:
            assert isinstance(
                chi := written_nexus_file["/entry/sample/sample_chi/chi"], h5py.Dataset
            )
            assert chi[:] == scan.chi_start_deg
            assert isinstance(
                phi := written_nexus_file["/entry/sample/sample_phi/phi"], h5py.Dataset
            )
            assert phi[:] == scan.phi_start_deg
            assert isinstance(
                omega := written_nexus_file["/entry/sample/sample_omega/omega"],
                h5py.Dataset,
            )
            omega = omega[:]
            assert isinstance(
                omega_end := written_nexus_file["/entry/sample/sample_omega/omega_end"],
                h5py.Dataset,
            )
            omega_end = omega_end[:]
            assert len(omega) == scan.num_images
            expected_omega_starts = np.linspace(
                scan.omega_start_deg,
                scan.omega_start_deg
                + ((scan.num_images - 1) * multi_params.rotation_increment_deg),
                scan.num_images,
            )
            assert np.allclose(omega, expected_omega_starts)
            expected_omega_ends = (
                expected_omega_starts + multi_params.rotation_increment_deg
            )
            assert np.allclose(omega_end, expected_omega_ends)
            assert isinstance(
                omega_transform := written_nexus_file[
                    "/entry/sample/transformations/omega"
                ],
                h5py.Dataset,
            )
            assert isinstance(omega_vec := omega_transform.attrs["vector"], np.ndarray)
            omega_flip = (
                feature_flags_update_with_omega_flip.mock_calls[0].args[0].omega_flip
            )
            assert tuple(omega_vec) == (-1.0 if omega_flip else 1.0, 0, 0)


@patch(
    "mx_bluesky.hyperion.external_interaction.callbacks.rotation.ispyb_callback.StoreInIspyb"
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.rotation_scan_plan.check_topup_and_wait_if_necessary",
    autospec=True,
)
def test_full_multi_rotation_plan_ispyb_called_correctly(
    _,
    mock_ispyb_store: MagicMock,
    RE: RunEngine,
    test_multi_rotation_params: MultiRotationScan,
    fake_create_rotation_devices: RotationScanComposite,
    oav_parameters_for_rotation: OAVParameters,
    ispyb_config_path: str,
):
    callback = RotationISPyBCallback()
    mock_ispyb_store.return_value = MagicMock(spec=StoreInIspyb)
    _run_multi_rotation_plan(
        RE,
        test_multi_rotation_params,
        fake_create_rotation_devices,
        [callback],
        oav_parameters_for_rotation,
    )
    ispyb_calls = mock_ispyb_store.call_args_list
    for instantiation_call, ispyb_store_calls, _ in zip(
        ispyb_calls,
        [  # there should be 4 calls to the IspybStore per run
            mock_ispyb_store.return_value.method_calls[i * 4 : (i + 1) * 4]
            for i in range(len(test_multi_rotation_params.rotation_scans))
        ],
        test_multi_rotation_params.single_rotation_scans,
        strict=False,
    ):
        assert instantiation_call.args[0] == ispyb_config_path
        assert ispyb_store_calls[0][0] == "begin_deposition"
        assert ispyb_store_calls[1][0] == "update_deposition"
        assert ispyb_store_calls[2][0] == "update_deposition"
        assert ispyb_store_calls[3][0] == "end_deposition"


@patch(
    "mx_bluesky.hyperion.experiment_plans.rotation_scan_plan.check_topup_and_wait_if_necessary",
    autospec=True,
)
def test_full_multi_rotation_plan_ispyb_interaction_end_to_end(
    _,
    mock_ispyb_conn_multiscan,
    RE: RunEngine,
    test_multi_rotation_params: MultiRotationScan,
    fake_create_rotation_devices: RotationScanComposite,
    oav_parameters_for_rotation: OAVParameters,
):
    number_of_scans = len(test_multi_rotation_params.rotation_scans)
    callback = RotationISPyBCallback()
    _run_multi_rotation_plan(
        RE,
        test_multi_rotation_params,
        fake_create_rotation_devices,
        [callback],
        oav_parameters_for_rotation,
    )
    mx = mx_acquisition_from_conn(mock_ispyb_conn_multiscan)
    assert mx.get_data_collection_group_params.call_count == number_of_scans
    assert mx.get_data_collection_params.call_count == number_of_scans * 4
    upsert_keys = mx.get_data_collection_params()
    for upsert_calls, rotation_params in zip(
        [  # there should be 4 datacollection upserts per scan
            mx.upsert_data_collection.call_args_list[i * 4 : (i + 1) * 4]
            for i in range(len(test_multi_rotation_params.rotation_scans))
        ],
        test_multi_rotation_params.single_rotation_scans,
        strict=False,
    ):
        first_upsert_data = remap_upsert_columns(upsert_keys, upsert_calls[0].args[0])
        assert (
            first_upsert_data["axisend"] - first_upsert_data["axisstart"]
            == rotation_params.scan_width_deg
        )
        assert first_upsert_data["nimages"] == rotation_params.num_images
        second_upsert_data = remap_upsert_columns(upsert_keys, upsert_calls[1].args[0])
        dc_id = second_upsert_data["id"]
        append_comment_call = next(
            dropwhile(
                lambda c: c.args[0] != dc_id,
                mx.update_data_collection_append_comments.mock_calls,
            )
        )
        comment = append_comment_call.args[1]
        assert comment.startswith("Sample position")
        position_string = f"{rotation_params.x_start_um:.0f}, {rotation_params.y_start_um:.0f}, {rotation_params.z_start_um:.0f}"
        assert position_string in comment
        third_upsert_data = remap_upsert_columns(upsert_keys, upsert_calls[2].args[0])
        assert third_upsert_data["resolution"] > 0  # resolution
        assert third_upsert_data["focalspotsizeatsamplex"] > 0  # beam size
        fourth_upsert_data = remap_upsert_columns(upsert_keys, upsert_calls[3].args[0])
        assert fourth_upsert_data["endtime"]  # timestamp
        assert fourth_upsert_data["runstatus"] == "DataCollection Successful"


@patch(
    "mx_bluesky.hyperion.experiment_plans.rotation_scan_plan.check_topup_and_wait_if_necessary",
    autospec=True,
)
def test_full_multi_rotation_plan_arms_eiger_asynchronously_and_disarms(
    _,
    RE: RunEngine,
    test_multi_rotation_params: MultiRotationScan,
    fake_create_rotation_devices: RotationScanComposite,
    oav_parameters_for_rotation: OAVParameters,
):
    eiger = fake_create_rotation_devices.eiger
    eiger.stage = MagicMock(return_value=Status(done=True, success=True))
    eiger.unstage = MagicMock(return_value=Status(done=True, success=True))
    eiger.do_arm.set = MagicMock(return_value=Status(done=True, success=True))

    _run_multi_rotation_plan(
        RE,
        test_multi_rotation_params,
        fake_create_rotation_devices,
        [],
        oav_parameters_for_rotation,
    )
    # Stage will arm the eiger synchonously
    eiger.stage.assert_not_called()

    eiger.do_arm.set.assert_called_once()
    eiger.unstage.assert_called_once()


@patch(
    "mx_bluesky.hyperion.external_interaction.callbacks.rotation.ispyb_callback.StoreInIspyb"
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.rotation_scan_plan.check_topup_and_wait_if_necessary",
    autospec=True,
)
def test_zocalo_callback_end_only_gets_called_at_the_end_of_all_collections(
    _,
    mock_ispyb_store: MagicMock,
    RE: RunEngine,
    test_multi_rotation_params: MultiRotationScan,
    fake_create_rotation_devices: RotationScanComposite,
    oav_parameters_for_rotation: OAVParameters,
):
    """We must unstage the detector before we trigger zocalo so that we're sure we've
    finished writing data."""
    mock_ispyb_store.return_value = MagicMock(spec=StoreInIspyb)
    mock_ispyb_store.return_value.begin_deposition.return_value = IspybIds(
        data_collection_ids=(123,)
    )
    eiger = fake_create_rotation_devices.eiger
    parent_mock = MagicMock()
    parent_mock.eiger = MagicMock(return_value=Status(done=True, success=True))
    eiger.unstage = parent_mock.eiger_unstage
    _, ispyb_callback = create_rotation_callbacks()
    zocalo_callback = ispyb_callback.emit_cb
    assert isinstance(zocalo_callback, ZocaloCallback)
    zocalo_callback.zocalo_interactor = MagicMock()
    zocalo_callback.zocalo_interactor.run_end = parent_mock.run_end

    _run_multi_rotation_plan(
        RE,
        test_multi_rotation_params,
        fake_create_rotation_devices,
        [ispyb_callback],
        oav_parameters_for_rotation,
    )

    assert parent_mock.method_calls.count(call.run_end(123)) == len(
        test_multi_rotation_params.rotation_scans
    )
    assert parent_mock.method_calls[0] == call.eiger_unstage


@patch(
    "mx_bluesky.hyperion.external_interaction.callbacks.rotation.ispyb_callback.StoreInIspyb"
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.rotation_scan_plan.check_topup_and_wait_if_necessary",
    autospec=True,
)
def test_zocalo_start_and_end_not_triggered_if_ispyb_ids_not_present(
    _,
    mock_ispyb_store: MagicMock,
    RE: RunEngine,
    test_multi_rotation_params: MultiRotationScan,
    fake_create_rotation_devices: RotationScanComposite,
    oav_parameters_for_rotation: OAVParameters,
):
    _, ispyb_callback = create_rotation_callbacks()
    zocalo_callback = ispyb_callback.emit_cb
    assert isinstance(zocalo_callback, ZocaloCallback)
    zocalo_callback.zocalo_interactor = (zocalo_trigger := MagicMock())

    ispyb_callback.ispyb = MagicMock(spec=StoreInIspyb)
    with pytest.raises(ISPyBDepositionNotMade):
        _run_multi_rotation_plan(
            RE,
            test_multi_rotation_params,
            fake_create_rotation_devices,
            [ispyb_callback],
            oav_parameters_for_rotation,
        )

    zocalo_trigger.run_start.assert_not_called()  # type: ignore


@patch(
    "mx_bluesky.hyperion.external_interaction.callbacks.rotation.ispyb_callback.StoreInIspyb"
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.rotation_scan_plan.check_topup_and_wait_if_necessary",
    autospec=True,
)
def test_ispyb_triggered_before_zocalo(
    _,
    mock_ispyb_store: MagicMock,
    RE: RunEngine,
    test_multi_rotation_params: MultiRotationScan,
    fake_create_rotation_devices: RotationScanComposite,
    oav_parameters_for_rotation: OAVParameters,
):
    _, ispyb_callback = create_rotation_callbacks()
    parent_mock = MagicMock()

    mock_ispyb_store.return_value = MagicMock(spec=StoreInIspyb)
    mock_ispyb_store.return_value.begin_deposition = parent_mock.ispyb_begin
    mock_ispyb_store.return_value.begin_deposition.return_value = IspybIds(
        data_collection_ids=(123,)
    )

    zocalo_callback = ispyb_callback.emit_cb
    assert isinstance(zocalo_callback, ZocaloCallback)
    zocalo_callback.zocalo_interactor = MagicMock()
    zocalo_callback.zocalo_interactor.run_start = parent_mock.zocalo_start

    _run_multi_rotation_plan(
        RE,
        test_multi_rotation_params,
        fake_create_rotation_devices,
        [ispyb_callback],
        oav_parameters_for_rotation,
    )

    call_names = [call[0] for call in parent_mock.method_calls]

    assert "ispyb_begin" in call_names
    assert "zocalo_start" in call_names

    assert call_names.index("ispyb_begin") < call_names.index("zocalo_start")


@patch(
    "mx_bluesky.hyperion.external_interaction.callbacks.rotation.ispyb_callback.StoreInIspyb"
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.rotation_scan_plan.check_topup_and_wait_if_necessary",
    autospec=True,
)
def test_zocalo_start_and_end_called_once_for_each_collection(
    _,
    mock_ispyb_store: MagicMock,
    RE: RunEngine,
    test_multi_rotation_params: MultiRotationScan,
    fake_create_rotation_devices: RotationScanComposite,
    oav_parameters_for_rotation: OAVParameters,
):
    _, ispyb_callback = create_rotation_callbacks()

    mock_ispyb_store.return_value = MagicMock(spec=StoreInIspyb)
    mock_ispyb_store.return_value.begin_deposition.return_value = IspybIds(
        data_collection_ids=(123,)
    )

    zocalo_callback = ispyb_callback.emit_cb
    assert isinstance(zocalo_callback, ZocaloCallback)
    zocalo_callback.zocalo_interactor = MagicMock()

    _run_multi_rotation_plan(
        RE,
        test_multi_rotation_params,
        fake_create_rotation_devices,
        [ispyb_callback],
        oav_parameters_for_rotation,
    )

    assert zocalo_callback.zocalo_interactor.run_start.call_count == len(
        test_multi_rotation_params.rotation_scans
    )
    assert zocalo_callback.zocalo_interactor.run_end.call_count == len(
        test_multi_rotation_params.rotation_scans
    )


def test_multi_rotation_scan_does_not_change_transmission_back_until_after_data_collected(
    fake_create_rotation_devices: RotationScanComposite,
    test_multi_rotation_params: MultiRotationScan,
    sim_run_engine_for_rotation: RunEngineSimulator,
    oav_parameters_for_rotation: OAVParameters,
):
    msgs = sim_run_engine_for_rotation.simulate_plan(
        rotation_scan(
            fake_create_rotation_devices,
            test_multi_rotation_params,
            oav_parameters_for_rotation,
        )
    )
    msgs = assert_message_and_return_remaining(
        msgs,
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


def test_multi_rotation_scan_does_not_verify_undulator_gap_until_before_run(
    fake_create_rotation_devices: RotationScanComposite,
    test_multi_rotation_params: MultiRotationScan,
    sim_run_engine_for_rotation: RunEngineSimulator,
    oav_parameters_for_rotation: OAVParameters,
):
    msgs = sim_run_engine_for_rotation.simulate_plan(
        rotation_scan(
            fake_create_rotation_devices,
            test_multi_rotation_params,
            oav_parameters_for_rotation,
        )
    )
    msgs = assert_message_and_return_remaining(
        msgs, lambda msg: msg.command == "set" and msg.obj.name == "undulator"
    )
    msgs = assert_message_and_return_remaining(
        msgs, lambda msg: msg.command == "open_run"
    )
