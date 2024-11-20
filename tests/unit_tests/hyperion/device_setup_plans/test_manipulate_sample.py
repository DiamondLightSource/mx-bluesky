from unittest.mock import MagicMock, call, patch

import numpy as np
import pytest
from bluesky.run_engine import RunEngine
from dodal.devices.aperturescatterguard import ApertureScatterguard, ApertureValue

from mx_bluesky.hyperion.device_setup_plans.manipulate_sample import (
    move_aperture_if_required,
)
from mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan import (
    FlyScanXRayCentreComposite,
)
from mx_bluesky.hyperion.parameters.gridscan import HyperionThreeDGridScan


@pytest.mark.parametrize(
    "set_position",
    [
        (ApertureValue.SMALL),
        (ApertureValue.MEDIUM),
        (ApertureValue.ROBOT_LOAD),
        (ApertureValue.LARGE),
    ],
)
async def test_move_aperture_goes_to_correct_position(
    aperture_scatterguard: ApertureScatterguard,
    RE: RunEngine,
    set_position,
):
    with patch.object(aperture_scatterguard, "set") as mock_set:
        RE(move_aperture_if_required(aperture_scatterguard, set_position))
        mock_set.assert_called_once_with(
            set_position,
        )


async def test_move_aperture_does_nothing_when_none_selected(
    aperture_scatterguard: ApertureScatterguard, RE: RunEngine
):
    with patch.object(aperture_scatterguard, "set") as mock_set:
        RE(move_aperture_if_required(aperture_scatterguard, None))
        mock_set.assert_not_called()


@patch("bluesky.plan_stubs.abs_set", autospec=True)
def test_results_passed_to_move_motors(
    bps_abs_set: MagicMock,
    test_fgs_params: HyperionThreeDGridScan,
    fake_fgs_composite: FlyScanXRayCentreComposite,
    RE: RunEngine,
):
    from mx_bluesky.hyperion.device_setup_plans.manipulate_sample import move_x_y_z

    motor_position = test_fgs_params.FGS_params.grid_position_to_motor_position(
        np.array([1, 2, 3])
    )
    RE(move_x_y_z(fake_fgs_composite.sample_motors, *motor_position))
    bps_abs_set.assert_has_calls(
        [
            call(
                fake_fgs_composite.sample_motors.x,
                motor_position[0],
                group="move_x_y_z",
            ),
            call(
                fake_fgs_composite.sample_motors.y,
                motor_position[1],
                group="move_x_y_z",
            ),
            call(
                fake_fgs_composite.sample_motors.z,
                motor_position[2],
                group="move_x_y_z",
            ),
        ],
        any_order=True,
    )
