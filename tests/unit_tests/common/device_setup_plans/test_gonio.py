import pytest
from bluesky.run_engine import RunEngine
from dodal.devices.motors import XYZOmegaStage
from ophyd_async.core import set_mock_value

from mx_bluesky.common.device_setup_plans.gonio import find_nearest_omega_360


@pytest.mark.parametrize(
    "current, expected",
    [
        # exact multiples
        (0, 0),
        (360, 360),
        (-360, -360),
        # near positives
        (10, 0),
        (200, 360),
        # near negatives
        (-10, 0),
        (-200, -360),
        # halfway cases
        (180, 0),
        (-180, 0),
        (540, 720),
        (-540, -720),
    ],
)
def test_nearest_omega_halfway(
    run_engine: RunEngine, smargon: XYZOmegaStage, current: float, expected: float
):
    set_mock_value(smargon.omega.user_readback, current)
    result = run_engine(find_nearest_omega_360(smargon))
    assert result.plan_result == expected  # type: ignore
