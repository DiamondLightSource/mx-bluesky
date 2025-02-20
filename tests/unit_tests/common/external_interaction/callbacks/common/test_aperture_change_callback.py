import pytest
from bluesky.run_engine import RunEngine
from dodal.devices.aperturescatterguard import (
    ApertureScatterguard,
)

from mx_bluesky.common.external_interaction.callbacks.common.aperture_change_callback import (
    ApertureChangeCallback,
)
from mx_bluesky.hyperion.experiment_plans.change_aperture_then_move_plan import (
    set_aperture_for_bbox_mm,
)


@pytest.mark.parametrize(
    "bbox, expected_aperture",
    [
        ([0.05, 0.05, 0.05], "LARGE_APERTURE"),
        ([0.02, 0.02, 0.02], "MEDIUM_APERTURE"),
    ],
    ids=["large_aperture", "medium_aperture"],
)
def test_aperture_change_callback(
    aperture_scatterguard: ApertureScatterguard,
    bbox: list[float],
    expected_aperture: str,
):
    cb = ApertureChangeCallback()
    RE = RunEngine({})
    RE.subscribe(cb)
    RE(set_aperture_for_bbox_mm(aperture_scatterguard, bbox))
    assert cb.last_selected_aperture == expected_aperture
