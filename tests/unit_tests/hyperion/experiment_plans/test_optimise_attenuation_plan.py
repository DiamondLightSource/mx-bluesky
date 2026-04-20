import asyncio
from typing import Literal
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from bluesky.run_engine import RunEngine
from dodal.beamlines import i03
from ophyd.status import Status
from ophyd_async.core import AsyncStatus
from ophyd_async.testing import set_mock_value

from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.hyperion.experiment_plans import optimise_attenuation_plan
from mx_bluesky.hyperion.experiment_plans.optimise_attenuation_plan import (
    AttenuationOptimisationFailedException,
    Direction,
    OptimizeAttenuationComposite,
    calculate_new_direction,
    check_parameters,
    deadtime_calc_new_transmission,
    deadtime_optimisation,
    is_counts_within_target,
    is_deadtime_optimised,
    total_counts_optimisation,
)


@pytest.fixture
def mock_emit():
    import logging

    test_handler = logging.Handler()
    test_handler.emit = MagicMock()  # type: ignore
    LOGGER.addHandler(test_handler)

    yield test_handler.emit

    LOGGER.removeHandler(test_handler)


@pytest.fixture
async def fake_composite(attenuator) -> OptimizeAttenuationComposite:
    sample_shutter = i03.sample_shutter(connect_immediately=True, mock=True)
    xspress3mini = i03.xspress3mini(connect_immediately=True, mock=True)

    return OptimizeAttenuationComposite(
        sample_shutter=sample_shutter, xspress3mini=xspress3mini, attenuator=attenuator
    )


def get_good_status():
    status = Status()
    status.set_finished()
    return status


@pytest.fixture
def fake_composite_mocked_sets(fake_composite: OptimizeAttenuationComposite):
    with (
        patch.object(
            fake_composite.xspress3mini,
            "stage",
            MagicMock(return_value=get_good_status()),
        ),
        patch.object(
            fake_composite.sample_shutter,
            "set",
            MagicMock(return_value=get_good_status()),
        ),
    ):
        yield fake_composite


def test_is_deadtime_optimised_returns_true_once_direction_is_flipped_and_deadtime_goes_back_above_threshold(
    RE: RunEngine,
):
    deadtime: float = 1
    direction = Direction.POSITIVE
    for _ in range(5):
        assert is_deadtime_optimised(deadtime, 0.5, 0.5, 1, Direction.POSITIVE) is False
        direction = calculate_new_direction(direction, deadtime, 0.5)
        deadtime -= 0.1
    assert direction == Direction.NEGATIVE
    deadtime = 0.4
    assert is_deadtime_optimised(deadtime, 0.5, 0.5, 1, direction) is True


def test_is_deadtime_is_optimised_logs_warning_when_upper_transmission_limit_is_reached(
    mock_emit: MagicMock,
):
    is_deadtime_optimised(0.5, 0.4, 0.9, 0.9, Direction.POSITIVE)
    latest_record = mock_emit.call_args.args[-1]
    assert latest_record.levelname == "WARNING"


def test_total_counts_calc_new_transmission_raises_warning_on_high_transmission(
    RE: RunEngine,
    mock_emit: MagicMock,
    fake_composite_mocked_sets: OptimizeAttenuationComposite,
):
    set_mock_value(
        fake_composite_mocked_sets.xspress3mini.dt_corrected_latest_mca[1],
        np.array([1, 1, 1, 1, 1, 1]),
    )
    RE(
        total_counts_optimisation(
            fake_composite_mocked_sets,
            transmission=0.1,
            low_roi=0,
            high_roi=1,
            lower_count_limit=0,
            upper_count_limit=0.1,
            target_count=1,
            max_cycles=1,
            upper_transmission_limit=0.1,
            lower_transmission_limit=0,
        )
    )

    latest_record = mock_emit.call_args.args[-1]
    assert latest_record.levelname == "WARNING"


@pytest.mark.parametrize(
    "old_direction, deadtime, deadtime_threshold, new_direction",
    [
        (Direction.POSITIVE, 0.1, 0.9, Direction.POSITIVE),
        (Direction.NEGATIVE, 0.5, 0.4, Direction.NEGATIVE),
    ],
)
def test_calculate_new_direction_gives_correct_value(
    old_direction: Direction | Direction,
    deadtime: float,
    deadtime_threshold: float,
    new_direction: Direction | Direction,
):
    assert (
        calculate_new_direction(old_direction, deadtime, deadtime_threshold)
        == new_direction
    )


@patch(
    "mx_bluesky.hyperion.experiment_plans.optimise_attenuation_plan.do_device_optimise_iteration",
    autospec=True,
)
def test_deadtime_optimisation_calculates_deadtime_correctly(
    mock_do_device_optimise_iteration,
    RE: RunEngine,
    fake_composite: OptimizeAttenuationComposite,
):
    set_mock_value(fake_composite.xspress3mini.channels[1].total_time, 100)
    set_mock_value(fake_composite.xspress3mini.channels[1].reset_ticks, 101)

    with patch(
        "mx_bluesky.hyperion.experiment_plans.optimise_attenuation_plan.is_deadtime_optimised",
        autospec=True,
    ) as mock_is_deadtime_optimised:
        RE(
            deadtime_optimisation(
                fake_composite,
                0.5,
                2,
                0.01,
                1,
                0.1,
                1e-6,
            )
        )
        mock_is_deadtime_optimised.assert_called_with(
            0.99, 0.01, 0.5, 0.1, Direction.POSITIVE
        )


@pytest.mark.parametrize(
    "target, upper_limit, lower_limit, default_high_roi, default_low_roi,initial_transmission,upper_transmission,lower_transmission",
    [
        (100, 90, 110, 1, 0, 0.5, 1, 0),
        (50, 100, 20, 10, 20, 0.5, 1, 0),
        (100, 100, 101, 10, 1, 0.5, 1, 0),
        (10, 100, 0, 2, 1, 0.5, 0, 1),
        (10, 100, 0, 2, 1, 0.5, 0.4, 0.1),
    ],
)
def test_check_parameters_fail_on_out_of_range_parameters(
    target: Literal[100] | Literal[50] | Literal[10],
    upper_limit: Literal[90] | Literal[100],
    lower_limit: Literal[110] | Literal[20] | Literal[101] | Literal[0],
    default_high_roi: Literal[1] | Literal[10] | Literal[2],
    default_low_roi: Literal[0] | Literal[20] | Literal[1],
    initial_transmission: float,
    upper_transmission: float | Literal[1] | Literal[0],
    lower_transmission: float | Literal[0] | Literal[1],
):
    with pytest.raises(ValueError):
        check_parameters(
            target,
            upper_limit,
            lower_limit,
            default_high_roi,
            default_low_roi,
            initial_transmission,
            upper_transmission,
            lower_transmission,
        )


def test_check_parameters_runs_on_correct_params():
    assert check_parameters(10, 100, 0, 2, 1, 0.5, 1, 0) is None


@pytest.mark.parametrize(
    "total_count, lower_limit, upper_limit",
    [(100, 99, 100), (100, 100, 100), (50, 25, 1000)],
)
def test_is_counts_within_target_is_true(
    total_count: Literal[100] | Literal[50],
    lower_limit: Literal[99] | Literal[100] | Literal[25],
    upper_limit: Literal[100] | Literal[1000],
):
    assert is_counts_within_target(total_count, lower_limit, upper_limit) is True


@pytest.mark.parametrize(
    "total_count, lower_limit, upper_limit",
    [(100, 101, 101), (0, 1, 2), (1000, 2000, 3000)],
)
def test_is_counts_within_target_is_false(
    total_count: Literal[100] | Literal[0] | Literal[1000],
    lower_limit: Literal[101] | Literal[1] | Literal[2000],
    upper_limit: Literal[101] | Literal[2] | Literal[3000],
):
    assert is_counts_within_target(total_count, lower_limit, upper_limit) is False


def test_total_count_exception_raised_after_max_cycles_reached(
    RE: RunEngine, fake_composite_mocked_sets: OptimizeAttenuationComposite
):
    optimise_attenuation_plan.is_counts_within_target = MagicMock(return_value=False)
    set_mock_value(
        fake_composite_mocked_sets.xspress3mini.dt_corrected_latest_mca[1],
        np.array([1, 1, 1, 1, 1, 1]),
    )
    with pytest.raises(AttenuationOptimisationFailedException):
        RE(
            total_counts_optimisation(
                fake_composite_mocked_sets, 1, 0, 10, 0, 5, 2, 1, 0, 0
            )
        )


@pytest.mark.parametrize(
    "direction, transmission, increment, upper_limit, lower_limit, new_transmission",
    [
        (Direction.POSITIVE, 0.5, 2, 0.9, 1e-6, 0.9),
        (Direction.POSITIVE, 0.1, 2, 0.9, 1e-6, 0.2),
        (Direction.NEGATIVE, 0.8, 2, 0.9, 1e-6, 0.4),
    ],
)
def test_deadtime_calc_new_transmission_gets_correct_value(
    direction: Direction | Direction,
    transmission: float,
    increment: Literal[2],
    upper_limit: float,
    lower_limit: float,
    new_transmission: float,
):
    assert (
        deadtime_calc_new_transmission(
            direction, transmission, increment, upper_limit, lower_limit
        )
        == new_transmission
    )


def test_deadtime_calc_new_transmission_raises_error_on_low_ransmission():
    with pytest.raises(AttenuationOptimisationFailedException):
        deadtime_calc_new_transmission(Direction.NEGATIVE, 1e-6, 2, 1, 1e-6)


def test_total_count_calc_new_transmission_raises_error_on_low_ransmission(
    RE: RunEngine, fake_composite_mocked_sets: OptimizeAttenuationComposite
):
    set_mock_value(
        fake_composite_mocked_sets.xspress3mini.dt_corrected_latest_mca[1],
        np.array([1, 1, 1, 1, 1, 1]),
    )
    with pytest.raises(AttenuationOptimisationFailedException):
        RE(
            total_counts_optimisation(
                fake_composite_mocked_sets,
                1e-6,
                0,
                1,
                10,
                20,
                1,
                1,
                0.5,
                0.1,
            )
        )


def test_total_counts_gets_within_target(
    RE: RunEngine,
    fake_composite_mocked_sets: OptimizeAttenuationComposite,
):
    # For simplicity we just increase the data array each iteration. In reality it's the transmission value that affects the array
    def update_data(value):
        nonlocal iteration
        iteration += 1
        set_mock_value(
            fake_composite_mocked_sets.xspress3mini.dt_corrected_latest_mca[1],
            np.array(([50, 50, 50, 50, 50]) * iteration),
        )
        return AsyncStatus(asyncio.sleep(0))

    fake_composite_mocked_sets.attenuator.set = update_data
    iteration = 0

    RE(
        total_counts_optimisation(
            fake_composite_mocked_sets,
            transmission=1,
            low_roi=0,
            high_roi=4,
            lower_count_limit=1000,
            upper_count_limit=2000,
            target_count=1500,
            max_cycles=10,
            upper_transmission_limit=1,
            lower_transmission_limit=0,
        )
    )


@pytest.mark.parametrize(
    "optimisation_type",
    [("total_counts"), ("deadtime")],
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.optimise_attenuation_plan.total_counts_optimisation",
    autospec=True,
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.optimise_attenuation_plan.deadtime_optimisation",
    autospec=True,
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.optimise_attenuation_plan.check_parameters",
    autospec=True,
)
def test_optimisation_attenuation_plan_runs_correct_functions(
    mock_check_parameters,
    mock_deadtime_optimisation,
    mock_total_counts_optimisation,
    optimisation_type: Literal["total_counts"] | Literal["deadtime"],
    RE: RunEngine,
    fake_composite: OptimizeAttenuationComposite,
):
    fake_composite.attenuator.set = MagicMock(return_value=get_good_status())
    fake_composite.xspress3mini.acquire_time.set = MagicMock(
        return_value=get_good_status()
    )

    RE(
        optimise_attenuation_plan.optimise_attenuation_plan(
            fake_composite,
            optimisation_type=optimisation_type,
        )
    )

    if optimisation_type == "total_counts":
        mock_deadtime_optimisation.assert_not_called()
        mock_total_counts_optimisation.assert_called_once()
    else:
        mock_total_counts_optimisation.assert_not_called()
        mock_deadtime_optimisation.assert_called_once()
    fake_composite.attenuator.set.assert_called_once()
    mock_check_parameters.assert_called_once()
    fake_composite.xspress3mini.acquire_time.set.assert_called_once()
