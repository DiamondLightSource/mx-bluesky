from types import SimpleNamespace

import pytest
from bluesky import RunEngine
from dodal.devices.aperturescatterguard import ApertureScatterguard, ApertureValue
from ophyd_async.core import get_mock_put

from mx_bluesky.beamlines.phase1.beamsize.phase1_aperture_scatterguard import (
    ApertureScatterguardComposite,
    Phase1ApertureScatterguardPlans,
)


@pytest.fixture
def beamsize_devices(aperture_scatterguard: ApertureScatterguard):
    return SimpleNamespace(aperture_scatterguard=aperture_scatterguard)


@pytest.mark.parametrize(
    "set_position",
    [
        (ApertureValue.SMALL),
        (ApertureValue.MEDIUM),
        (ApertureValue.OUT_OF_BEAM),
        (ApertureValue.LARGE),
    ],
)
async def test_perform_beam_size_goes_to_correct_position(
    beamsize_devices: ApertureScatterguardComposite,
    run_engine: RunEngine,
    set_position: ApertureValue,
):
    plans = Phase1ApertureScatterguardPlans()
    run_engine(plans.perform_beam_size(beamsize_devices, set_position, "test_group"))
    last_pos = get_mock_put(
        beamsize_devices.aperture_scatterguard.selected_aperture
    ).call_args[0]
    assert last_pos == (set_position,)


async def test_perform_beam_size_does_nothing_when_none_selected(
    beamsize_devices: ApertureScatterguardComposite, run_engine: RunEngine
):
    plans = Phase1ApertureScatterguardPlans()
    get_mock_put(beamsize_devices.aperture_scatterguard.selected_aperture).reset_mock()
    run_engine(plans.perform_beam_size(beamsize_devices, None, "test_group"))
    mock_put = get_mock_put(beamsize_devices.aperture_scatterguard.selected_aperture)
    mock_put.assert_not_called()
