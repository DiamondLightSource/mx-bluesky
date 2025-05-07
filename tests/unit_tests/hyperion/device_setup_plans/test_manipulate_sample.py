from unittest.mock import MagicMock, call, patch

import pytest
from bluesky.run_engine import RunEngine
from dodal.devices.aperturescatterguard import ApertureScatterguard, ApertureValue
from ophyd_async.testing import get_mock_put

from mx_bluesky.common.device_setup_plans.manipulate_sample import (
    move_aperture_if_required,
    move_phi_chi_omega,
    move_x_y_z,
)
from mx_bluesky.hyperion.parameters.device_composites import (
    HyperionFlyScanXRayCentreComposite,
)


@pytest.mark.parametrize(
    "set_position",
    [
        (ApertureValue.SMALL),
        (ApertureValue.MEDIUM),
        (ApertureValue.OUT_OF_BEAM),
        (ApertureValue.LARGE),
    ],
)
async def test_move_aperture_goes_to_correct_position(
    aperture_scatterguard: ApertureScatterguard,
    RE: RunEngine,
    set_position,
):
    RE(move_aperture_if_required(aperture_scatterguard, set_position))
    last_pos = get_mock_put(aperture_scatterguard.selected_aperture).call_args[0]
    assert last_pos == (set_position,)


async def test_move_aperture_does_nothing_when_none_selected(
    aperture_scatterguard: ApertureScatterguard, RE: RunEngine
):
    get_mock_put(aperture_scatterguard.selected_aperture).reset_mock()
    RE(move_aperture_if_required(aperture_scatterguard, None))
    mock_put = get_mock_put(aperture_scatterguard.selected_aperture)
    mock_put.assert_not_called()


@pytest.mark.parametrize(
    "motor_position, expected_moves",
    [
        [[1, 2, 3], [1, 2, 3]],
        [[0, 0, 0], [None, None, None]],
        [[None, None, None], [None, None, None]],
        [[1, 0, 0], [1, 0, 0]],
        [[0, 1, 0], [0, 1, 0]],
        [[0, 0, 1], [0, 0, 1]],
        [[1, None, None], [1, None, None]],
        [[None, 1, None], [None, 1, None]],
        [[None, None, 1], [None, None, 1]],
    ],
)
@patch("bluesky.plan_stubs.abs_set", autospec=True)
def test_move_x_y_z(
    bps_abs_set: MagicMock,
    fake_fgs_composite: HyperionFlyScanXRayCentreComposite,
    RE: RunEngine,
    motor_position: list[float],
    expected_moves: list[float | None],
):
    RE(move_x_y_z(fake_fgs_composite.smargon, *motor_position))  # type: ignore
    expected_calls = [
        call(axis, pos, group="move_x_y_z")
        for axis, pos in zip(
            [
                fake_fgs_composite.smargon.x,
                fake_fgs_composite.smargon.y,
                fake_fgs_composite.smargon.z,
            ],
            expected_moves,
            strict=False,
        )
        if pos is not None
    ]
    bps_abs_set.assert_has_calls(
        expected_calls,
        any_order=True,
    )


@pytest.mark.parametrize(
    "motor_position, expected_moves",
    [
        [[1, 2, 3], [1, 2, 3]],
        [[0, 0, 0], [0, 0, 0]],
        [[0, None, None], [0, None, None]],
        [[None, 0, None], [None, 0, None]],
        [[None, None, 0], [None, None, 0]],
        [[None, None, None], [None, None, None]],
        [[1, 0, 0], [1, 0, 0]],
    ],
)
@patch("bluesky.plan_stubs.abs_set", autospec=True)
def test_move_phi_chi_omega(
    bps_abs_set: MagicMock,
    fake_fgs_composite: HyperionFlyScanXRayCentreComposite,
    RE: RunEngine,
    motor_position: list[float],
    expected_moves: list[float | None],
):
    RE(move_phi_chi_omega(fake_fgs_composite.smargon, *motor_position))  # type: ignore
    expected_calls = [
        call(axis, pos, group="move_phi_chi_omega")
        for axis, pos in zip(
            [
                fake_fgs_composite.smargon.phi,
                fake_fgs_composite.smargon.chi,
                fake_fgs_composite.smargon.omega,
            ],
            expected_moves,
            strict=False,
        )
        if pos is not None
    ]
    bps_abs_set.assert_has_calls(
        expected_calls,
        any_order=True,
    )
