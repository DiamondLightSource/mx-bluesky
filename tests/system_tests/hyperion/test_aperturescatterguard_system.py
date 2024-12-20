import pytest
from dodal.common.beamlines.beamline_parameters import (
    BEAMLINE_PARAMETER_PATHS,
    GDABeamlineParameters,
)
from dodal.devices.aperturescatterguard import (
    AperturePosition,
    ApertureScatterguard,
    load_positions_from_beamline_parameters,
)
from ophyd_async.core import DeviceCollector

from mx_bluesky.hyperion.experiment_plans.change_aperture_then_move_plan import (
    set_aperture_for_bbox_mm,
)


@pytest.fixture
def ap_sg():
    params = GDABeamlineParameters.from_file(BEAMLINE_PARAMETER_PATHS["i03"])
    with DeviceCollector():
        ap_sg = ApertureScatterguard(
            prefix="BL03S",
            name="ap_sg",
            loaded_positions=load_positions_from_beamline_parameters(params),
            tolerances=AperturePosition.tolerances_from_gda_params(params),
        )
    return ap_sg


@pytest.mark.s03()
@pytest.mark.parametrize(
    "bbox, expected_aperture",
    [
        ([0.05, 0.05, 0.05], "LARGE_APERTURE"),
        ([0.02, 0.02, 0.02], "MEDIUM_APERTURE"),
    ],
    ids=["large_aperture", "medium_aperture"],
)
def test_aperture_change_callback(
    ap_sg: ApertureScatterguard, bbox: list[float], expected_aperture: str
):
    from bluesky.run_engine import RunEngine

    from mx_bluesky.hyperion.external_interaction.callbacks.aperture_change_callback import (
        ApertureChangeCallback,
    )

    cb = ApertureChangeCallback()
    RE = RunEngine({})
    RE.subscribe(cb)
    RE(set_aperture_for_bbox_mm(ap_sg, bbox))
    assert cb.last_selected_aperture == expected_aperture
