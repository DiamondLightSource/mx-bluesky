from dodal.common.beamlines.beamline_parameters import BEAMLINE_PARAMETER_PATHS

BEAMLINE_PARAMETER_PATHS["test"] = BEAMLINE_PARAMETER_PATHS["i03"]
from dodal.beamlines.i03 import *  # type: ignore  # noqa: E402, F403
