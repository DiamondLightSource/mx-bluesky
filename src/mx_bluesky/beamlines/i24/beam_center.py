"""Where the beam lands on a detector at i24, as a function of how far away it is.

The lookup tables are maintained per detector in daq_configuration, from processed
data - "take values from autoprocessing results in SynchWeb", as the files themselves
put it - so a newly commissioned detector has no table until it has been collected on.
"""

from pathlib import Path

from daq_config_server.models.lookup_tables import DetectorXYLookupTable
from dodal.common.beamlines.beamline_utils import get_config_client
from dodal.devices.util.lookup_tables import linear_interpolation_lut

LUT_FILES_PATH = Path("/dls_sw/i24/software/daq_configuration/lookup")

JUNGFRAU_BEAM_CENTER_LUT = LUT_FILES_PATH / "DetDistToBeamXYConverterJF9M.txt"


def beam_center_mm_from_lut(
    lut_path: Path, detector_distance_mm: float
) -> tuple[float, float]:
    """The beam centre, in mm, at this detector distance.

    Args:
        lut_path: The detector's distance-to-beam-XY table.
        detector_distance_mm: How far away the detector is.

    Returns:
        Beam centre x and y, in mm, interpolated between the table's entries.
    """
    lut_columns = (
        get_config_client().get_file_contents(lut_path, DetectorXYLookupTable).columns
    )
    beam_x_mm = linear_interpolation_lut(lut_columns[0], lut_columns[1])(
        detector_distance_mm
    )
    beam_y_mm = linear_interpolation_lut(lut_columns[0], lut_columns[2])(
        detector_distance_mm
    )
    return beam_x_mm, beam_y_mm
