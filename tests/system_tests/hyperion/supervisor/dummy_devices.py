from dodal.common.beamlines.beamline_parameters import BEAMLINE_PARAMETER_PATHS

BEAMLINE_PARAMETER_PATHS["i03"] = "tests/test_data/test_beamline_parameters.txt"
from dodal.beamlines.i03 import *  # type: ignore  # noqa: E402, F403
