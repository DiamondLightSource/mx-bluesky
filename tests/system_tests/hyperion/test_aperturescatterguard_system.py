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
from ophyd_async.core import init_devices


@pytest.fixture
def ap_sg():
    params = GDABeamlineParameters.from_file(BEAMLINE_PARAMETER_PATHS["i03"])
    with init_devices():
        ap_sg = ApertureScatterguard(
            prefix="BL03S",
            name="ap_sg",
            loaded_positions=load_positions_from_beamline_parameters(params),
            tolerances=AperturePosition.tolerances_from_gda_params(params),
        )
    return ap_sg
