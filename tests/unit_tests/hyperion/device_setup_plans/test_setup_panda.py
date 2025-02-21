import os
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from bluesky.plan_stubs import null
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from dodal.common.types import UpdatingPathProvider
from dodal.devices.fast_grid_scan import PandAGridScanParams
from dodal.devices.smargon import Smargon
from ophyd_async.fastcs.panda import HDFPanda, SeqTable, SeqTrigger

from mx_bluesky.common.parameters.constants import DeviceSettingsConstants
from mx_bluesky.hyperion.device_setup_plans.setup_panda import (
    MM_TO_ENCODER_COUNTS,
    PULSE_WIDTH_US,
    disarm_panda_for_gridscan,
    set_panda_directory,
    setup_panda_for_flyscan,
)


def get_smargon_speed(x_step_size_mm: float, time_between_x_steps_ms: float) -> float:
    return x_step_size_mm / time_between_x_steps_ms


def run_simulating_setup_panda_functions(
    plan: str,
    panda: HDFPanda,
    smargon: Smargon,
):
    num_of_sets = 0
    num_of_waits = 0

    def count_commands(msg):
        nonlocal num_of_sets
        nonlocal num_of_waits
        if msg.command == "set":
            num_of_sets += 1
        elif msg.command == "wait":
            num_of_waits += 1

    sim = RunEngineSimulator()
    sim.add_handler(["set", "wait"], count_commands)

    with patch(
        "mx_bluesky.hyperion.device_setup_plans.setup_panda.load_panda_from_yaml"
    ) as mock_load_panda:
        if plan == "setup":
            smargon_speed = get_smargon_speed(0.1, 1)
            sim.simulate_plan(
                setup_panda_for_flyscan(
                    panda,
                    PandAGridScanParams(transmission_fraction=0.01),
                    smargon,
                    0.1,
                    100.1,
                    smargon_speed,
                )
            )
            mock_load_panda.assert_called_once()
        elif plan == "disarm":
            sim.simulate_plan(disarm_panda_for_gridscan(panda))

    return num_of_sets, num_of_waits


def test_setup_panda_performs_correct_plans(sim_run_engine, panda, smargon):
    num_of_sets, num_of_waits = run_simulating_setup_panda_functions(
        "setup", panda, smargon
    )
    assert num_of_sets == 10
    assert num_of_waits == 5


@pytest.mark.parametrize(
    "x_steps, x_step_size, x_start, run_up_distance_mm, time_between_x_steps_ms, exposure_time_s",
    [
        (10, 0.2, 0, 0.5, 10.001, 0.01),
        (10, 0.5, -1, 0.05, 10.001, 0.01),
        (1, 2, 1.2, 1, 100.001, 0.1),
        (10, 2, -0.5, 3, 101, 0.1),
    ],
)
@patch("mx_bluesky.hyperion.device_setup_plans.setup_panda.load_panda_from_yaml")
def test_setup_panda_correctly_configures_table(
    mock_load_panda,
    x_steps: int,
    x_step_size: float,
    x_start: float,
    run_up_distance_mm: float,
    time_between_x_steps_ms: float,
    exposure_time_s: float,
    sim_run_engine: RunEngineSimulator,
    panda,
    smargon,
):
    sample_velocity_mm_per_s = get_smargon_speed(x_step_size, time_between_x_steps_ms)
    params = PandAGridScanParams(
        x_steps=x_steps,
        x_step_size_mm=x_step_size,
        x_start_mm=x_start,
        run_up_distance_mm=run_up_distance_mm,
        transmission_fraction=0.01,
    )

    exposure_distance_mm = sample_velocity_mm_per_s * exposure_time_s

    msgs = sim_run_engine.simulate_plan(
        setup_panda_for_flyscan(
            panda,
            params,
            smargon,
            exposure_time_s,
            time_between_x_steps_ms,
            sample_velocity_mm_per_s,
        )
    )

    # ignore all loading operations related to loading saved panda state from yaml
    msgs = [
        msg for msg in msgs if not msg.kwargs.get("group", "").startswith("load-phase")
    ]

    assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "panda-pulse-1-width"
        and msg.args[0] == exposure_time_s,
    )

    table_msg = [
        msg
        for msg in msgs
        if msg.command == "set" and msg.obj.name == "panda-seq-1-table"
    ][0]

    table = table_msg.args[0]
    SPACE_WIDTH_US = int(time_between_x_steps_ms * 1000 - PULSE_WIDTH_US)

    exposure_distance_counts = exposure_distance_mm * MM_TO_ENCODER_COUNTS
    expected_seq_table: SeqTable = (
        SeqTable.row(
            repeats=1,
            trigger=SeqTrigger.BITA_1,
            position=0,
            time1=False,
            outa1=False,
            time2=True,
            outa2=False,
        )
        + SeqTable.row(
            repeats=x_steps,
            trigger=SeqTrigger.POSA_GT,
            position=int(params.x_start_mm * MM_TO_ENCODER_COUNTS),
            time1=PULSE_WIDTH_US,
            outa1=True,
            time2=SPACE_WIDTH_US,
            outa2=False,
        )
        + SeqTable.row(
            repeats=1,
            trigger=SeqTrigger.BITA_1,
            position=0,
            time1=False,
            outa1=False,
            time2=True,
            outa2=False,
        )
        + SeqTable.row(
            repeats=x_steps,
            trigger=SeqTrigger.POSA_LT,
            position=int(
                (params.x_start_mm + (params.x_steps - 1) * params.x_step_size_mm)
                * MM_TO_ENCODER_COUNTS
                + exposure_distance_counts
            ),
            time1=PULSE_WIDTH_US,
            outa1=True,
            time2=SPACE_WIDTH_US,
            outa2=False,
        )
    )

    for attr_name in table.__annotations__.keys():
        np.testing.assert_array_equal(
            getattr(table, attr_name), getattr(expected_seq_table, attr_name)
        )


def test_wait_between_setting_table_and_arming_panda(RE: RunEngine, panda, smargon):
    bps_wait_done = False

    def handle_wait(*args, **kwargs):
        nonlocal bps_wait_done
        bps_wait_done = True
        yield from null()

    def assert_set_table_has_been_waited_on(*args, **kwargs):
        assert bps_wait_done
        yield from null()

    with (
        patch(
            "mx_bluesky.hyperion.device_setup_plans.setup_panda.arm_panda_for_gridscan",
            MagicMock(side_effect=assert_set_table_has_been_waited_on),
        ),
        patch(
            "mx_bluesky.hyperion.device_setup_plans.setup_panda.bps.wait",
            MagicMock(side_effect=handle_wait),
        ),
        patch(
            "mx_bluesky.hyperion.device_setup_plans.setup_panda.load_panda_from_yaml"
        ),
        patch("mx_bluesky.hyperion.device_setup_plans.setup_panda.bps.abs_set"),
    ):
        RE(
            setup_panda_for_flyscan(
                panda,
                PandAGridScanParams(transmission_fraction=0.01),
                smargon,
                0.1,
                101.1,
                get_smargon_speed(0.1, 1),
            )
        )

    assert bps_wait_done


# It also would be useful to have some system tests which check that (at least)
# all the blocks which were enabled on setup are also disabled on tidyup
def test_disarm_panda_disables_correct_blocks(sim_run_engine, panda, smargon):
    num_of_sets, num_of_waits = run_simulating_setup_panda_functions(
        "disarm", panda, smargon
    )
    assert num_of_sets == 5
    assert num_of_waits == 1


@patch("mx_bluesky.hyperion.device_setup_plans.setup_panda.get_path_provider")
@patch("mx_bluesky.hyperion.device_setup_plans.setup_panda.datetime", spec=datetime)
def test_set_panda_directory(
    mock_datetime, mock_get_path_provider: MagicMock, tmp_path, RE
):
    mock_directory_provider = MagicMock(spec=UpdatingPathProvider)
    mock_datetime.now = MagicMock(
        return_value=datetime.fromisoformat("2024-08-11T15:59:23")
    )
    mock_get_path_provider.return_value = mock_directory_provider

    RE(set_panda_directory(tmp_path))
    mock_directory_provider.update.assert_called_with(
        directory=tmp_path, suffix="_20240811155923"
    )


def test_panda_settings_exist():
    # Panda settings are found relative to the top of the repo so this should
    # work in prod as well as test

    panda_settings_location = Path(
        DeviceSettingsConstants.PANDA_FLYSCAN_SETTINGS_DIR,
        f"{DeviceSettingsConstants.PANDA_FLYSCAN_SETTINGS_FILENAME}.yaml",
    )
    assert os.path.exists(panda_settings_location)
