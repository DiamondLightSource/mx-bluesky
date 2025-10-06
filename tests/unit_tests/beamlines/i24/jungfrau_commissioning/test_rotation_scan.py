import asyncio
from unittest.mock import MagicMock, patch

import pytest
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from dodal.devices.hutch_shutter import ShutterState
from dodal.devices.i24.aperture import AperturePositions
from dodal.devices.i24.beamstop import BeamstopPositions
from dodal.devices.i24.dual_backlight import BacklightPositions
from ophyd_async.testing import set_mock_value

from mx_bluesky.beamlines.i24.jungfrau_commissioning.plan_utils import JF_COMPLETE_GROUP
from mx_bluesky.beamlines.i24.jungfrau_commissioning.rotation_scan_plan import (
    DEFAULT_DETECTOR_DISTANCE_MM,
    JF_DET_STAGE_Y_POSITION_MM,
    HutchClosedException,
    RotationScanComposite,
    _cleanup_plan,
    multi_rotation_plan_varying_transmission,
    set_up_beamline_for_rotation,
    single_rotation_plan,
)
from mx_bluesky.beamlines.i24.parameters.constants import PlanNameConstants
from mx_bluesky.beamlines.i24.parameters.rotation import (
    MultiRotationScanByTransmissions,
)
from mx_bluesky.common.experiment_plans.rotation.rotation_utils import (
    calculate_motion_profile,
)
from mx_bluesky.common.parameters.constants import PlanGroupCheckpointConstants
from tests.conftest import raw_params_from_file
from tests.unit_tests.beamlines.i24.jungfrau_commissioning.utils import (
    get_good_single_rotation_params,
)


def get_good_multi_rotation_params(transmissions: list[float], tmp_path):
    params = raw_params_from_file(
        "tests/unit_tests/beamlines/i24/jungfrau_commissioning/test_data/test_good_rotation_params.json",
        tmp_path,
    )
    del params["transmission_frac"]
    params["transmission_fractions"] = [0.2, 0.4, 0.6]
    return MultiRotationScanByTransmissions(**params)


@patch(
    "mx_bluesky.beamlines.i24.jungfrau_commissioning.rotation_scan_plan.read_devices_for_metadata"
)
@patch(
    "mx_bluesky.beamlines.i24.jungfrau_commissioning.rotation_scan_plan._cleanup_plan"
)
@patch(
    "mx_bluesky.beamlines.i24.jungfrau_commissioning.rotation_scan_plan.check_topup_and_wait_if_necessary"
)
@patch("mx_bluesky.beamlines.i24.jungfrau_commissioning.rotation_scan_plan.arm_zebra")
@patch(
    "mx_bluesky.beamlines.i24.jungfrau_commissioning.rotation_scan_plan.setup_zebra_for_rotation"
)
@patch(
    "mx_bluesky.beamlines.i24.jungfrau_commissioning.rotation_scan_plan.calculate_motion_profile"
)
@patch(
    "mx_bluesky.beamlines.i24.jungfrau_commissioning.rotation_scan_plan.set_up_beamline_for_rotation"
)
@patch(
    "mx_bluesky.beamlines.i24.jungfrau_commissioning.rotation_scan_plan.fly_jungfrau"
)
async def test_single_rotation_plan_in_re(
    mock_fly: MagicMock,
    mock_setup_beamline: MagicMock,
    mock_calc_motion_profile: MagicMock,
    mock_setup_zebra: MagicMock,
    mock_arm_zebra: MagicMock,
    mock_check_topup: MagicMock,
    mock_cleanup: MagicMock,
    mock_metadata_read: MagicMock,
    RE: RunEngine,
    tmp_path,
    rotation_composite: RotationScanComposite,
):
    # Test correct functions are called, but don't test bluesky messages
    params = get_good_single_rotation_params(tmp_path)
    mock_calc_motion_profile.return_value = calculate_motion_profile(params, 1, 1)
    RE(single_rotation_plan(rotation_composite, params))
    mock_setup_beamline.assert_called_once_with(
        rotation_composite, DEFAULT_DETECTOR_DISTANCE_MM, 0.1
    )
    mock_calc_motion_profile.assert_called_once_with(
        params, 1, await rotation_composite.gonio.omega.max_velocity.get_value()
    )
    mock_setup_zebra.assert_called_once()
    mock_arm_zebra.assert_called_once()
    mock_check_topup.assert_called_once()
    mock_metadata_read.assert_called_once()
    mock_fly.assert_called_once()
    mock_cleanup.assert_called_once()


@patch(
    "mx_bluesky.beamlines.i24.jungfrau_commissioning.rotation_scan_plan.check_topup_and_wait_if_necessary"
)
@patch(
    "mx_bluesky.beamlines.i24.jungfrau_commissioning.rotation_scan_plan.set_up_beamline_for_rotation"
)
@patch(
    "mx_bluesky.beamlines.i24.jungfrau_commissioning.rotation_scan_plan.fly_jungfrau"
)
def test_single_rotation_plan_in_simulator(
    _mock_fly: MagicMock,
    _mock_set_up_beamline_for_rotation: MagicMock,
    _mock_topup: MagicMock,
    sim_run_engine: RunEngineSimulator,
    rotation_composite: RotationScanComposite,
    tmp_path,
):
    params = get_good_single_rotation_params(tmp_path)
    set_mock_value(rotation_composite.hutch_shutter.status, ShutterState.OPEN)
    msgs = sim_run_engine.simulate_plan(
        single_rotation_plan(rotation_composite, params)
    )

    assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "open_run"
        and msg.run == "OUTER SINGLE ROTATION SCAN",
    )

    # Wait for rotation devices to be ready before reading metadata
    assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "wait"
        and msg.kwargs["group"] == PlanGroupCheckpointConstants.ROTATION_READY_FOR_DC,
    )
    assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "create"
        and msg.kwargs["name"] == PlanNameConstants.ROTATION_META_READ,
    )

    # Set omega axis then wait for JF to complete
    assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set" and msg.obj == rotation_composite.gonio.omega,
    )
    assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "wait" and msg.kwargs["group"] == JF_COMPLETE_GROUP,
    )

    # Unstage JF and close run
    assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "unstage" and msg.obj == rotation_composite.jungfrau,
    )
    assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "close_run"
        and msg.run == PlanNameConstants.SINGLE_ROTATION_SCAN,
    )


@patch(
    "mx_bluesky.beamlines.i24.jungfrau_commissioning.rotation_scan_plan.single_rotation_plan"
)
def test_multi_rotation_plan_in_re(
    mock_single_rotation: MagicMock,
    RE: RunEngine,
    tmp_path,
    rotation_composite: RotationScanComposite,
):
    desired_transmission_fracs = [0.2, 0.4, 0.6]
    params = get_good_multi_rotation_params(desired_transmission_fracs, tmp_path)
    set_mock_value(rotation_composite.jungfrau._writer.frame_counter, params.num_images)
    set_mock_value(rotation_composite.hutch_shutter.status, ShutterState.OPEN)
    RE(multi_rotation_plan_varying_transmission(rotation_composite, params))
    called_transmission_fracs = [
        mock_single_rotation.call_args_list[i].args[1].transmission_frac
        for i in range(mock_single_rotation.call_count)
    ]
    assert desired_transmission_fracs == called_transmission_fracs


async def test_set_up_beamline_for_rotation_success(
    rotation_composite: RotationScanComposite,
    RE: RunEngine,
):
    trans_frac = 0.1
    det_z = 200
    set_mock_value(rotation_composite.hutch_shutter.status, ShutterState.OPEN)
    RE(set_up_beamline_for_rotation(rotation_composite, det_z, trans_frac))

    assert await asyncio.gather(
        rotation_composite.aperture.position.get_value(),
        rotation_composite.beamstop.pos_select.get_value(),
        rotation_composite.det_stage.y.user_readback.get_value(),
        rotation_composite.backlight.backlight_position.pos_level.get_value(),
        rotation_composite.det_stage.z.user_readback.get_value(),
        rotation_composite.attenuator.actual_transmission.get_value(),
    ) == [
        AperturePositions.IN,
        BeamstopPositions.DATA_COLLECTION,
        JF_DET_STAGE_Y_POSITION_MM,
        BacklightPositions.OUT,
        det_z,
        trans_frac,
    ]


def test_set_up_beamline_for_rotation_error_on_closed_hutch(
    rotation_composite: RotationScanComposite,
    RE: RunEngine,
):
    trans_frac = 0.1
    det_z = 200
    set_mock_value(rotation_composite.hutch_shutter.status, ShutterState.CLOSED)
    with pytest.raises(HutchClosedException):
        RE(set_up_beamline_for_rotation(rotation_composite, det_z, trans_frac))


class FakeException(Exception): ...


@patch(
    "mx_bluesky.beamlines.i24.jungfrau_commissioning.rotation_scan_plan.check_topup_and_wait_if_necessary",
    new=MagicMock(side_effect=FakeException),  # Exit test early by inserting exception
)
@patch(
    "mx_bluesky.beamlines.i24.jungfrau_commissioning.rotation_scan_plan.set_up_beamline_for_rotation"
)
def test_single_rotation_plan_uses_default_if_no_det_distance(
    mock_set_up_beamline: MagicMock,
    sim_run_engine: RunEngineSimulator,
    rotation_composite: RotationScanComposite,
    tmp_path,
):
    params = get_good_single_rotation_params(tmp_path)
    params.detector_distance_mm = None
    with pytest.raises(FakeException):
        sim_run_engine.simulate_plan(single_rotation_plan(rotation_composite, params))
    mock_set_up_beamline.assert_called_once_with(
        rotation_composite, DEFAULT_DETECTOR_DISTANCE_MM, params.transmission_frac
    )


@patch(
    "mx_bluesky.beamlines.i24.jungfrau_commissioning.rotation_scan_plan.tidy_up_zebra_after_rotation_scan"
)
def test_cleanup_plan(
    mock_tidy_zebra: MagicMock, rotation_composite: RotationScanComposite, RE: RunEngine
):
    rotation_composite.jungfrau.unstage = MagicMock()
    RE(
        _cleanup_plan(
            rotation_composite.zebra,
            rotation_composite.jungfrau,
            rotation_composite.sample_shutter,
        )
    )
    mock_tidy_zebra.assert_called_once()
    rotation_composite.jungfrau.unstage.assert_called_once()
