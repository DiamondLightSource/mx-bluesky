from functools import partial
from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

import pytest
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from bluesky.utils import Msg
from dodal.devices.aperturescatterguard import ApertureScatterguard, ApertureValue
from dodal.devices.backlight import BacklightPosition
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.smargon import Smargon, StubPosition
from dodal.devices.webcam import Webcam
from ophyd.sim import NullStatus
from ophyd_async.testing import get_mock_put, set_mock_value

from mx_bluesky.hyperion.experiment_plans.robot_load_and_change_energy import (
    RobotLoadAndEnergyChangeComposite,
    prepare_for_robot_load,
    robot_load_and_change_energy_plan,
    take_robot_snapshots,
)
from mx_bluesky.hyperion.external_interaction.callbacks.robot_load.ispyb_callback import (
    RobotLoadISPyBCallback,
)
from mx_bluesky.hyperion.parameters.robot_load import RobotLoadAndEnergyChange

from ....conftest import raw_params_from_file


@pytest.fixture
def robot_load_and_energy_change_params():
    params = raw_params_from_file(
        "tests/test_data/parameter_json_files/good_test_robot_load_params.json"
    )
    return RobotLoadAndEnergyChange(**params)


@pytest.fixture
def robot_load_and_energy_change_params_no_energy(robot_load_and_energy_change_params):
    robot_load_and_energy_change_params.demand_energy_ev = None
    return robot_load_and_energy_change_params


def dummy_set_energy_plan(energy, composite):
    return (yield Msg("set_energy_plan"))


@patch(
    "mx_bluesky.hyperion.experiment_plans.robot_load_and_change_energy.set_energy_plan",
    MagicMock(side_effect=dummy_set_energy_plan),
)
def test_when_plan_run_with_requested_energy_specified_energy_change_executes(
    robot_load_and_energy_change_composite: RobotLoadAndEnergyChangeComposite,
    robot_load_and_energy_change_params: RobotLoadAndEnergyChange,
    sim_run_engine: RunEngineSimulator,
):
    sim_run_engine.add_handler(
        "read",
        lambda msg: {"dcm-energy_in_kev": {"value": 11.105}},
        "dcm-energy_in_kev",
    )
    messages = sim_run_engine.simulate_plan(
        robot_load_and_change_energy_plan(
            robot_load_and_energy_change_composite, robot_load_and_energy_change_params
        )
    )
    assert_message_and_return_remaining(
        messages, lambda msg: msg.command == "set_energy_plan"
    )


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
        robot_load_and_change_energy_plan(
            robot_load_composite, robot_load_then_centre_params
        )
    )


@pytest.mark.parametrize("total_disabled_reads", [5, 3, 14])
@patch(
    "mx_bluesky.hyperion.experiment_plans.robot_load_and_change_energy.set_energy_plan",
    MagicMock(return_value=iter([])),
)
def test_given_smargon_disabled_when_plan_run_then_waits_on_smargon(
    robot_load_and_energy_change_composite: RobotLoadAndEnergyChangeComposite,
    robot_load_and_energy_change_params: RobotLoadAndEnergyChange,
    total_disabled_reads: int,
    sim_run_engine,
):
    messages = run_simulating_smargon_wait(
        robot_load_and_energy_change_params,
        robot_load_and_energy_change_composite,
        total_disabled_reads,
        sim_run_engine,
    )

    sleep_messages = filter(lambda msg: msg.command == "sleep", messages)
    read_disabled_messages = filter(
        lambda msg: msg.command == "read" and msg.obj.name == "smargon-disabled",
        messages,
    )

    assert len(list(sleep_messages)) == total_disabled_reads - 1
    assert len(list(read_disabled_messages)) == total_disabled_reads


@pytest.mark.timeout(2)
@patch(
    "mx_bluesky.hyperion.experiment_plans.robot_load_and_change_energy.set_energy_plan",
    MagicMock(return_value=iter([])),
)
def test_given_smargon_disabled_for_longer_than_timeout_when_plan_run_then_throws_exception(
    robot_load_and_energy_change_composite: RobotLoadAndEnergyChangeComposite,
    robot_load_and_energy_change_params: RobotLoadAndEnergyChange,
    sim_run_engine,
):
    with pytest.raises(TimeoutError):
        run_simulating_smargon_wait(
            robot_load_and_energy_change_params,
            robot_load_and_energy_change_composite,
            1000,
            sim_run_engine,
        )


async def test_when_prepare_for_robot_load_called_then_moves_as_expected(
    aperture_scatterguard: ApertureScatterguard, smargon: Smargon, done_status
):
    smargon.stub_offsets.set = MagicMock(return_value=done_status)
    get_mock_put(aperture_scatterguard.selected_aperture).reset_mock()

    set_mock_value(smargon.x.user_setpoint, 10)
    set_mock_value(smargon.z.user_setpoint, 5)
    set_mock_value(smargon.omega.user_setpoint, 90)

    RE = RunEngine()
    RE(prepare_for_robot_load(aperture_scatterguard, smargon))

    assert await smargon.x.user_setpoint.get_value() == 0
    assert await smargon.z.user_setpoint.get_value() == 0
    assert await smargon.omega.user_setpoint.get_value() == 0

    smargon.stub_offsets.set.assert_called_once_with(StubPosition.RESET_TO_ROBOT_LOAD)  # type: ignore
    get_mock_put(aperture_scatterguard.selected_aperture).assert_called_once_with(
        ApertureValue.OUT_OF_BEAM, wait=ANY
    )


@patch(
    "mx_bluesky.hyperion.external_interaction.callbacks.robot_load.ispyb_callback.ExpeyeInteraction"
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.robot_load_and_change_energy.set_energy_plan",
    MagicMock(return_value=iter([])),
)
def test_given_ispyb_callback_attached_when_robot_load_then_centre_plan_called_then_ispyb_deposited(
    exp_eye: MagicMock,
    robot_load_and_energy_change_composite: RobotLoadAndEnergyChangeComposite,
    robot_load_and_energy_change_params: RobotLoadAndEnergyChange,
):
    set_mock_value(
        robot_load_and_energy_change_composite.oav.snapshot.last_saved_path,
        "test_oav_snapshot",
    )  # type: ignore
    set_mock_value(
        robot_load_and_energy_change_composite.webcam.last_saved_path,
        "test_webcam_snapshot",
    )
    robot_load_and_energy_change_composite.webcam.trigger = MagicMock(
        return_value=NullStatus()
    )

    RE = RunEngine()
    RE.subscribe(RobotLoadISPyBCallback())

    action_id = 1098
    exp_eye.return_value.start_load.return_value = action_id

    RE(
        robot_load_and_change_energy_plan(
            robot_load_and_energy_change_composite, robot_load_and_energy_change_params
        )
    )

    exp_eye.return_value.start_load.assert_called_once_with("cm31105", 4, 12345, 40, 3)
    exp_eye.return_value.update_barcode_and_snapshots.assert_called_once_with(
        action_id, "BARCODE", "test_webcam_snapshot", "test_oav_snapshot"
    )
    exp_eye.return_value.end_load.assert_called_once_with(action_id, "success", "OK")


@patch("mx_bluesky.hyperion.experiment_plans.robot_load_and_change_energy.datetime")
async def test_when_take_snapshots_called_then_filename_and_directory_set_and_device_triggered(
    mock_datetime: MagicMock, oav: OAV, webcam: Webcam
):
    TEST_DIRECTORY = "TEST"

    mock_datetime.now.return_value.strftime.return_value = "TIME"

    RE = RunEngine()
    oav.snapshot.trigger = MagicMock(side_effect=oav.snapshot.trigger)
    webcam.trigger = MagicMock(return_value=NullStatus())

    RE(take_robot_snapshots(oav, webcam, Path(TEST_DIRECTORY)))

    oav.snapshot.trigger.assert_called_once()
    assert await oav.snapshot.filename.get_value() == "TIME_oav-snapshot_after_load"
    assert await oav.snapshot.directory.get_value() == TEST_DIRECTORY

    webcam.trigger.assert_called_once()
    assert (await webcam.filename.get_value()) == "TIME_webcam_after_load"
    assert (await webcam.directory.get_value()) == TEST_DIRECTORY


def test_given_lower_gonio_moved_when_robot_load_then_lower_gonio_moved_to_home_and_back(
    robot_load_and_energy_change_composite: RobotLoadAndEnergyChangeComposite,
    robot_load_and_energy_change_params_no_energy: RobotLoadAndEnergyChange,
    sim_run_engine: RunEngineSimulator,
):
    initial_values = {"x": 0.11, "y": 0.12, "z": 0.13}

    def get_read(axis, msg):
        return {"readback": initial_values[axis]}

    for axis in initial_values.keys():
        sim_run_engine.add_handler(
            "locate", partial(get_read, axis), f"lower_gonio-{axis}"
        )

    messages = sim_run_engine.simulate_plan(
        robot_load_and_change_energy_plan(
            robot_load_and_energy_change_composite,
            robot_load_and_energy_change_params_no_energy,
        )
    )

    for axis in initial_values.keys():
        messages = assert_message_and_return_remaining(
            messages,
            lambda msg: msg.command == "set"
            and msg.obj.name == f"lower_gonio-{axis}"
            and msg.args == (0,),
        )

    for axis, initial in initial_values.items():
        messages = assert_message_and_return_remaining(
            messages,
            lambda msg: msg.command == "set"
            and msg.obj.name == f"lower_gonio-{axis}"
            and msg.args == (initial,),
        )


@patch(
    "mx_bluesky.hyperion.experiment_plans.robot_load_and_change_energy.set_energy_plan",
    MagicMock(return_value=iter([])),
)
def test_when_plan_run_then_lower_gonio_moved_before_robot_loads_and_back_after_smargon_enabled(
    robot_load_and_energy_change_composite: RobotLoadAndEnergyChangeComposite,
    robot_load_and_energy_change_params_no_energy: RobotLoadAndEnergyChange,
    sim_run_engine: RunEngineSimulator,
):
    initial_values = {"x": 0.11, "y": 0.12, "z": 0.13}

    def get_read(axis, msg):
        return {"readback": initial_values[axis]}

    for axis in initial_values.keys():
        sim_run_engine.add_handler(
            "locate", partial(get_read, axis), f"lower_gonio-{axis}"
        )

    messages = sim_run_engine.simulate_plan(
        robot_load_and_change_energy_plan(
            robot_load_and_energy_change_composite,
            robot_load_and_energy_change_params_no_energy,
        )
    )

    assert_message_and_return_remaining(
        messages, lambda msg: msg.command == "set" and msg.obj.name == "robot"
    )

    for axis in initial_values.keys():
        messages = assert_message_and_return_remaining(
            messages,
            lambda msg: msg.command == "set"
            and msg.obj.name == f"lower_gonio-{axis}"
            and msg.args == (0,),
        )

    assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "read" and msg.obj.name == "smargon-disabled",
    )

    for axis, initial in initial_values.items():
        messages = assert_message_and_return_remaining(
            messages,
            lambda msg: msg.command == "set"
            and msg.obj.name == f"lower_gonio-{axis}"  # noqa
            and msg.args == (initial,),  # noqa
        )


@patch(
    "mx_bluesky.hyperion.experiment_plans.robot_load_and_change_energy.set_energy_plan",
    MagicMock(return_value=iter([])),
)
def test_when_plan_run_then_thawing_turned_on_for_expected_time(
    robot_load_and_energy_change_composite: RobotLoadAndEnergyChangeComposite,
    robot_load_and_energy_change_params_no_energy: RobotLoadAndEnergyChange,
    sim_run_engine: RunEngineSimulator,
):
    robot_load_and_energy_change_params_no_energy.thawing_time = (thaw_time := 50)

    sim_run_engine.add_handler(
        "read",
        lambda msg: {"dcm-energy_in_kev": {"value": 11.105}},
        "dcm-energy_in_kev",
    )

    messages = sim_run_engine.simulate_plan(
        robot_load_and_change_energy_plan(
            robot_load_and_energy_change_composite,
            robot_load_and_energy_change_params_no_energy,
        )
    )

    assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "set"
        and msg.obj.name == "thawer-thaw_for_time_s"
        and msg.args[0] == thaw_time,
    )


@patch(
    "mx_bluesky.hyperion.experiment_plans.robot_load_and_change_energy.set_energy_plan",
    MagicMock(return_value=iter([])),
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.robot_load_and_change_energy.take_robot_snapshots",
    MagicMock(return_value=iter([Msg("take_robot_snapshots")])),
)
def test_when_plan_run_then_backlight_moved_in_before_snapshots_taken(
    robot_load_and_energy_change_composite: RobotLoadAndEnergyChangeComposite,
    robot_load_and_energy_change_params_no_energy: RobotLoadAndEnergyChange,
    sim_run_engine: RunEngineSimulator,
):
    sim_run_engine.add_handler(
        "read",
        lambda msg: {"dcm-energy_in_kev": {"value": 11.105}},
        "dcm-energy_in_kev",
    )

    messages = sim_run_engine.simulate_plan(
        robot_load_and_change_energy_plan(
            robot_load_and_energy_change_composite,
            robot_load_and_energy_change_params_no_energy,
        )
    )

    msgs = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "set"
        and msg.obj.name == "backlight"
        and msg.args[0] == BacklightPosition.IN,
    )

    backlight_move_group = msgs[0].kwargs.get("group")

    msgs = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "wait"
        and msg.kwargs["group"] == backlight_move_group,
    )

    assert_message_and_return_remaining(
        msgs, lambda msg: msg.command == "take_robot_snapshots"
    )
