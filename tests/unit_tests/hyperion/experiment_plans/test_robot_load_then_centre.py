from unittest.mock import MagicMock, patch

import pytest
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from bluesky.utils import Msg
from dodal.devices.i03 import BeamstopPositions
from dodal.devices.robot import SampleLocation

from mx_bluesky.common.device_setup_plans.check_beamstop import BeamstopException
from mx_bluesky.common.plans.common_flyscan_xray_centre_plan import (
    _fire_xray_centre_result_event,
)
from mx_bluesky.hyperion.experiment_plans.grid_detect_then_xray_centre_plan import (
    GridDetectThenXRayCentreComposite,
)
from mx_bluesky.hyperion.experiment_plans.robot_load_then_centre_plan import (
    RobotLoadThenCentreComposite,
    robot_load_then_xray_centre,
)
from mx_bluesky.hyperion.parameters.constants import CONST
from mx_bluesky.hyperion.parameters.gridscan import (
    PinTipCentreThenXrayCentre,
)
from mx_bluesky.hyperion.parameters.robot_load import RobotLoadThenCentre

from ....conftest import assert_none_matching, raw_params_from_file
from .conftest import FLYSCAN_RESULT_LOW, FLYSCAN_RESULT_MED, sim_fire_event_on_open_run


@pytest.fixture
def robot_load_then_centre_params():
    params = raw_params_from_file(
        "tests/test_data/parameter_json_files/good_test_robot_load_and_centre_params.json"
    )
    return RobotLoadThenCentre(**params)


@pytest.fixture
def robot_load_then_centre_params_no_energy(robot_load_then_centre_params):
    robot_load_then_centre_params.demand_energy_ev = None
    return robot_load_then_centre_params


@pytest.fixture
def sample_is_loaded(sim_run_engine, robot_load_then_centre_params):
    sample_location = SampleLocation(2, 6)
    robot_load_then_centre_params.sample_puck = sample_location.puck
    robot_load_then_centre_params.sample_pin = sample_location.pin
    mock_current_sample(sim_run_engine, sample_location)


@pytest.fixture
def sample_is_not_loaded(sim_run_engine, sample_is_loaded):
    mock_current_sample(sim_run_engine, SampleLocation(1, 1))


def mock_pin_centre_then_flyscan_plan(_, __, ___):
    yield from _fire_xray_centre_result_event([FLYSCAN_RESULT_MED, FLYSCAN_RESULT_LOW])


@patch(
    "mx_bluesky.hyperion.experiment_plans.robot_load_then_centre_plan.pin_centre_then_flyscan_plan",
    side_effect=mock_pin_centre_then_flyscan_plan,
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.robot_load_then_centre_plan.robot_load_and_change_energy_plan",
    MagicMock(return_value=iter([])),
)
def test_when_plan_run_then_centring_plan_run_with_expected_parameters(
    mock_centring_plan: MagicMock,
    robot_load_composite: RobotLoadThenCentreComposite,
    robot_load_then_centre_params: RobotLoadThenCentre,
):
    RE = RunEngine()

    RE(robot_load_then_xray_centre(robot_load_composite, robot_load_then_centre_params))
    composite_passed = mock_centring_plan.call_args[0][0]
    params_passed: PinTipCentreThenXrayCentre = mock_centring_plan.call_args[0][1]

    for name, value in vars(composite_passed).items():
        assert value == getattr(robot_load_composite, name)

    for name in GridDetectThenXRayCentreComposite.__dataclass_fields__.keys():
        assert getattr(composite_passed, name), f"{name} not in composite"

    assert isinstance(params_passed, PinTipCentreThenXrayCentre)
    assert params_passed.detector_params.expected_energy_ev == 11100


@patch(
    "mx_bluesky.hyperion.experiment_plans.robot_load_then_centre_plan.pin_centre_then_flyscan_plan",
    side_effect=mock_pin_centre_then_flyscan_plan,
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.robot_load_then_centre_plan.robot_load_and_change_energy_plan",
    MagicMock(return_value=iter([])),
)
def test_when_plan_run_with_requested_energy_specified_energy_set_on_eiger(
    mock_centring_plan: MagicMock,
    robot_load_composite: RobotLoadThenCentreComposite,
    robot_load_then_centre_params: RobotLoadThenCentre,
    sim_run_engine: RunEngineSimulator,
):
    robot_load_composite.eiger.set_detector_parameters = MagicMock()
    sim_run_engine.add_handler_for_callback_subscribes()
    sim_fire_event_on_open_run(sim_run_engine, CONST.PLAN.FLYSCAN_RESULTS)
    sim_run_engine.simulate_plan(
        robot_load_then_xray_centre(robot_load_composite, robot_load_then_centre_params)
    )
    det_params = robot_load_composite.eiger.set_detector_parameters.call_args[0][0]
    assert det_params.expected_energy_ev == 11100
    params_passed: PinTipCentreThenXrayCentre = mock_centring_plan.call_args[0][1]
    assert params_passed.detector_params.expected_energy_ev == 11100


@patch(
    "mx_bluesky.hyperion.experiment_plans.robot_load_then_centre_plan.pin_centre_then_flyscan_plan",
    MagicMock(side_effect=mock_pin_centre_then_flyscan_plan),
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.robot_load_then_centre_plan.robot_load_and_change_energy_plan",
    MagicMock(return_value=iter([])),
)
def test_given_no_energy_supplied_when_robot_load_then_centre_current_energy_set_on_eiger(
    robot_load_composite: RobotLoadThenCentreComposite,
    robot_load_then_centre_params_no_energy: RobotLoadThenCentre,
    sim_run_engine: RunEngineSimulator,
):
    robot_load_composite.eiger.set_detector_parameters = MagicMock()
    sim_run_engine.add_handler_for_callback_subscribes()
    sim_fire_event_on_open_run(sim_run_engine, CONST.PLAN.FLYSCAN_RESULTS)
    sim_run_engine.add_handler(
        "locate",
        lambda msg: {"readback": 11.105},
        "dcm-energy_in_kev",
    )
    sim_run_engine.simulate_plan(
        robot_load_then_xray_centre(
            robot_load_composite,
            robot_load_then_centre_params_no_energy,
        )
    )
    det_params = robot_load_composite.eiger.set_detector_parameters.call_args[0][0]
    assert det_params.expected_energy_ev == 11105


def run_simulating_smargon_wait(
    robot_load_then_centre_params,
    robot_load_composite,
    total_disabled_reads,
    sim_run_engine: RunEngineSimulator,
):
    num_of_reads = 0

    def return_not_disabled_after_reads(_):
        nonlocal num_of_reads
        num_of_reads += 1
        return {"values": {"value": int(num_of_reads < total_disabled_reads)}}

    sim_run_engine.add_handler(
        "locate",
        lambda msg: {"readback": 11.105},
        "dcm-energy_in_kev",
    )
    sim_run_engine.add_handler(
        "read", return_not_disabled_after_reads, "smargon-disabled"
    )

    return sim_run_engine.simulate_plan(
        robot_load_then_xray_centre(robot_load_composite, robot_load_then_centre_params)
    )


def dummy_robot_load_plan(*args, **kwargs):
    return (yield Msg("robot_load"))


@patch(
    "mx_bluesky.hyperion.experiment_plans.robot_load_then_centre_plan.pin_centre_then_flyscan_plan",
    MagicMock(side_effect=mock_pin_centre_then_flyscan_plan),
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.robot_load_then_centre_plan.robot_load_and_change_energy_plan",
    MagicMock(side_effect=dummy_robot_load_plan),
)
def test_when_plan_run_then_detector_arm_started_before_wait_on_robot_load(
    robot_load_composite: RobotLoadThenCentreComposite,
    robot_load_then_centre_params: RobotLoadThenCentre,
    sim_run_engine,
):
    sim_run_engine.add_handler_for_callback_subscribes()
    sim_fire_event_on_open_run(sim_run_engine, CONST.PLAN.FLYSCAN_RESULTS)
    messages = sim_run_engine.simulate_plan(
        robot_load_then_xray_centre(robot_load_composite, robot_load_then_centre_params)
    )
    messages = assert_message_and_return_remaining(
        messages, lambda msg: msg.command == "set" and msg.obj.name == "eiger_do_arm"
    )

    assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "robot_load",
    )


def mock_current_sample(sim_run_engine: RunEngineSimulator, sample: SampleLocation):
    sim_run_engine.add_handler(
        "read",
        lambda msg: {"robot-current_puck": {"value": sample.puck}},
        "robot-current_puck",
    )
    sim_run_engine.add_handler(
        "read",
        lambda msg: {"robot-current_pin": {"value": sample.pin}},
        "robot-current_pin",
    )


@patch(
    "mx_bluesky.hyperion.experiment_plans.robot_load_then_centre_plan.pin_centre_then_flyscan_plan",
    MagicMock(return_value=iter([Msg("centre_plan")])),
)
def test_given_sample_already_loaded_and_chi_not_changed_when_robot_load_called_then_eiger_not_staged_and_centring_not_run(
    robot_load_composite: RobotLoadThenCentreComposite,
    robot_load_then_centre_params: RobotLoadThenCentre,
    sim_run_engine: RunEngineSimulator,
    sample_is_loaded,
):
    sim_run_engine.add_handler_for_callback_subscribes()
    sim_fire_event_on_open_run(sim_run_engine, CONST.PLAN.FLYSCAN_RESULTS)
    robot_load_then_centre_params.chi_start_deg = None

    messages = sim_run_engine.simulate_plan(
        robot_load_then_xray_centre(
            robot_load_composite,
            robot_load_then_centre_params,
        )
    )

    assert_none_matching(
        messages, lambda msg: msg.command == "set" and msg.obj.name == "eiger_do_arm"
    )

    assert_none_matching(
        messages, lambda msg: msg.command == "set" and msg.obj.name == "robot"
    )

    assert_none_matching(
        messages,
        lambda msg: msg.command == "centre_plan",
    )


@patch(
    "mx_bluesky.hyperion.experiment_plans.robot_load_then_centre_plan.pin_centre_then_flyscan_plan",
    MagicMock(return_value=iter([Msg("centre_plan")])),
)
def test_given_sample_already_loaded_and_chi_is_changed_when_robot_load_called_then_eiger_staged_and_centring_run(
    robot_load_composite: RobotLoadThenCentreComposite,
    robot_load_then_centre_params: RobotLoadThenCentre,
    sim_run_engine: RunEngineSimulator,
    sample_is_loaded,
):
    sim_run_engine.add_handler_for_callback_subscribes()
    sim_fire_event_on_open_run(sim_run_engine, CONST.PLAN.FLYSCAN_RESULTS)
    robot_load_then_centre_params.chi_start_deg = 30

    messages = sim_run_engine.simulate_plan(
        robot_load_then_xray_centre(
            robot_load_composite,
            robot_load_then_centre_params,
        )
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "set" and msg.obj.name == "eiger_do_arm",
    )

    assert_none_matching(
        messages, lambda msg: msg.command == "set" and msg.obj.name == "robot"
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "centre_plan",
    )


@patch(
    "mx_bluesky.hyperion.experiment_plans.robot_load_then_centre_plan.pin_centre_then_flyscan_plan",
    MagicMock(return_value=iter([Msg("centre_plan")])),
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.robot_load_then_centre_plan.robot_load_and_change_energy_plan",
    MagicMock(return_value=iter([Msg("full_robot_load_plan")])),
)
def test_given_sample_not_loaded_and_chi_not_changed_when_robot_load_called_then_eiger_staged_before_robot_and_centring_run_after(
    robot_load_composite: RobotLoadThenCentreComposite,
    robot_load_then_centre_params: RobotLoadThenCentre,
    sim_run_engine: RunEngineSimulator,
    sample_is_not_loaded,
):
    sim_run_engine.add_handler_for_callback_subscribes()
    sim_fire_event_on_open_run(sim_run_engine, CONST.PLAN.FLYSCAN_RESULTS)
    robot_load_then_centre_params.chi_start_deg = None

    messages = sim_run_engine.simulate_plan(
        robot_load_then_xray_centre(
            robot_load_composite,
            robot_load_then_centre_params,
        )
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "set" and msg.obj.name == "eiger_do_arm",
    )

    messages = assert_message_and_return_remaining(
        messages, lambda msg: msg.command == "full_robot_load_plan"
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "centre_plan",
    )


@patch(
    "mx_bluesky.hyperion.experiment_plans.robot_load_then_centre_plan.pin_centre_then_flyscan_plan",
    MagicMock(return_value=iter([Msg("centre_plan")])),
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.robot_load_then_centre_plan.robot_load_and_change_energy_plan",
    MagicMock(return_value=iter([Msg("full_robot_load_plan")])),
)
def test_given_sample_not_loaded_and_chi_changed_when_robot_load_called_then_eiger_staged_before_robot_and_centring_run(
    robot_load_composite: RobotLoadThenCentreComposite,
    robot_load_then_centre_params: RobotLoadThenCentre,
    sim_run_engine: RunEngineSimulator,
    sample_is_not_loaded,
):
    sim_run_engine.add_handler_for_callback_subscribes()
    sim_fire_event_on_open_run(sim_run_engine, CONST.PLAN.FLYSCAN_RESULTS)
    robot_load_then_centre_params.chi_start_deg = 30

    messages = sim_run_engine.simulate_plan(
        robot_load_then_xray_centre(
            robot_load_composite,
            robot_load_then_centre_params,
        )
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "set" and msg.obj.name == "eiger_do_arm",
    )

    messages = assert_message_and_return_remaining(
        messages, lambda msg: msg.command == "full_robot_load_plan"
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "centre_plan",
    )


@patch(
    "mx_bluesky.hyperion.experiment_plans.robot_load_then_centre_plan.pin_centre_then_flyscan_plan",
    MagicMock(return_value=iter([Msg("centre_plan")])),
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.robot_load_then_centre_plan.set_energy_plan",
    MagicMock(
        side_effect=lambda energy, _: iter([Msg("set_energy_plan", None, energy)])
    ),
)
def test_robot_load_then_centre_sets_energy_when_chi_change_and_no_robot_load(
    sim_run_engine: RunEngineSimulator,
    robot_load_composite: RobotLoadThenCentreComposite,
    robot_load_then_centre_params: RobotLoadThenCentre,
    sample_is_loaded,
):
    robot_load_then_centre_params.chi_start_deg = 30

    messages = sim_run_engine.simulate_plan(
        robot_load_then_xray_centre(
            robot_load_composite,
            robot_load_then_centre_params,
        )
    )

    messages = assert_message_and_return_remaining(
        messages, lambda msg: msg.command == "set_energy_plan" and msg.args[0] == 11100
    )
    messages = assert_message_and_return_remaining(
        messages, lambda msg: msg.command == "centre_plan"
    )


@patch(
    "mx_bluesky.hyperion.experiment_plans.robot_load_then_centre_plan.set_energy_plan",
    MagicMock(
        side_effect=lambda energy, _: iter([Msg("set_energy_plan", None, energy)])
    ),
)
def test_robot_load_then_centre_sets_energy_when_no_robot_load_no_chi_change(
    sim_run_engine: RunEngineSimulator,
    robot_load_composite: RobotLoadThenCentreComposite,
    robot_load_then_centre_params: RobotLoadThenCentre,
    sample_is_loaded,
):
    robot_load_then_centre_params.chi_start_deg = None

    messages = sim_run_engine.simulate_plan(
        robot_load_then_xray_centre(
            robot_load_composite,
            robot_load_then_centre_params,
        )
    )
    messages = assert_message_and_return_remaining(
        messages, lambda msg: msg.command == "set_energy_plan" and msg.args[0] == 11100
    )


def test_tip_offset_um_passed_to_pin_tip_centre_plan(
    robot_load_then_centre_params: RobotLoadThenCentre,
):
    robot_load_then_centre_params.tip_offset_um = 100
    assert (
        robot_load_then_centre_params.pin_centre_then_xray_centre_params.tip_offset_um
        == 100
    )


def test_robot_load_then_centre_fails_with_exception_when_no_beamstop(
    sim_run_engine: RunEngineSimulator,
    robot_load_composite: RobotLoadThenCentreComposite,
    robot_load_then_centre_params: RobotLoadThenCentre,
):
    sim_run_engine.add_read_handler_for(
        robot_load_composite.beamstop.selected_pos, BeamstopPositions.UNKNOWN
    )
    with pytest.raises(BeamstopException):
        sim_run_engine.simulate_plan(
            robot_load_then_xray_centre(
                robot_load_composite, robot_load_then_centre_params
            )
        )


@pytest.mark.timeout(2)
@patch(
    "mx_bluesky.hyperion.experiment_plans.pin_centre_then_xray_centre_plan.detect_grid_and_do_gridscan"
)
def test_box_size_passed_through_to_gridscan(
    mock_detect_grid: MagicMock,
    robot_load_composite: RobotLoadThenCentreComposite,
    robot_load_then_centre_params: RobotLoadThenCentre,
    grid_detection_callback_with_detected_grid: MagicMock,
    RE: RunEngine,
):
    robot_load_then_centre_params.box_size_um = 25
    RE(
        robot_load_then_xray_centre(
            robot_load_composite,
            robot_load_then_centre_params,
        )
    )
    detect_grid_call = mock_detect_grid.mock_calls[0]
    assert detect_grid_call.args[1].box_size_um == 25
